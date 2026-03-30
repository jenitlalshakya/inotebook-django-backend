from backend.config.settings import FRONTEND_URL
import os
import json
import base64
import hmac
import hashlib
import uuid
from datetime import datetime, timedelta
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from bson import ObjectId
from core.mongo import users_collection
from accounts.utils import jwt_required

load_dotenv()
ESEWA_SECRET_KEY = os.getenv("ESEWA_SECRET_KEY")
ESEWA_PRODUCT_CODE = os.getenv("ESEWA_PRODUCT_CODE")

PLANS = {
    "free": {
        "name": "Free Plan",
        "notes_limit": 50,
        "storage_limit_mb": 100,
        "storage_limit_bytes": 100 * 1024 * 1024,
        "words_limit": 500,
        "file_upload_enabled": False,
        "price": 0,
        "duration_days": 0
    },
    "pro_monthly": {
        "name": "Pro Monthly",
        "notes_limit": 999999, # unlimited
        "storage_limit_mb": 5120, # 5GB
        "storage_limit_bytes": 5 * 1024 * 1024 * 1024,
        "words_limit": 999999, # unlimited
        "file_upload_enabled": True,
        "price": 299,
        "duration_days": 30
    },
    "pro_yearly": {
        "name": "Pro Yearly",
        "notes_limit": 999999,
        "storage_limit_mb": 5120,
        "storage_limit_bytes": 5 * 1024 * 1024 * 1024,
        "words_limit": 999999,
        "file_upload_enabled": True,
        "price": 2999,
        "duration_days": 365
    }
}

@csrf_exempt
def configs(request):
    if request.method == "GET":
        return JsonResponse({"success": True, "plans": PLANS}, status=200)
    return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

@csrf_exempt
@jwt_required
def initiate_payment(request):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Method not allowed. Use GET."}, status=405)
    
    try:
        selected_plan = request.GET.get("plan")
        
        if selected_plan not in ["pro_monthly", "pro_yearly"]:
            return HttpResponse("Invalid plan selected.", status=400)
            
        plan_config = PLANS[selected_plan]
        amount = str(plan_config["price"])
        
        # Embed user_id in transaction_uuid for stateless tracking
        # Format: {user_id}-{random_hex}
        # eSewa supports up to 100 chars for transaction_uuid
        random_part = uuid.uuid4().hex[:12]
        transaction_uuid = f"{request.user_id}-{random_part}"
        
        # Message string logic for eSewa ePay v2
        message = f"total_amount={amount},transaction_uuid={transaction_uuid},product_code={ESEWA_PRODUCT_CODE}"
        
        keys = bytes(ESEWA_SECRET_KEY, 'utf-8')
        message_bytes = bytes(message, 'utf-8')
        hmac_sha256 = hmac.new(keys, message_bytes, hashlib.sha256)
        signature = base64.b64encode(hmac_sha256.digest()).decode('utf-8')
        
        # Determine URLs
        # Assume server runs on localhost:8000
        host_url = request.build_absolute_uri('/')[:-1]
        success_url = f"{host_url}/api/subscription/success"
        failure_url = f"{host_url}/api/subscription/failure"
        
        context = {
            "amount": amount,
            "total_amount": amount,
            "transaction_uuid": transaction_uuid,
            "product_code": ESEWA_PRODUCT_CODE,
            "success_url": success_url,
            "failure_url": failure_url,
            "signed_field_names": "total_amount,transaction_uuid,product_code",
            "signature": signature,
        }
        
        return render(request, "subscription_form.html", context)
        
    except Exception as e:
        return HttpResponse(f"Error initiating payment: {str(e)}", status=500)

@csrf_exempt
def payment_success(request):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        encoded_data = request.GET.get("data")
        
        if not encoded_data:
            return HttpResponse("No payment data provided", status=400)
            
        decoded_string = base64.b64decode(encoded_data).decode('utf-8')
        esewa_res = json.loads(decoded_string)
        
        print("eSewa response:", esewa_res) # Log for backend testing
        
        signed_field_names = esewa_res.get("signed_field_names", "")
        if not signed_field_names:
            return HttpResponse("Invalid response from eSewa", status=400)
            
        fields = signed_field_names.split(",")
        message_parts = []
        for field in fields:
            message_parts.append(f"{field}={esewa_res.get(field, '')}")
        message = ",".join(message_parts)
        
        keys = bytes(ESEWA_SECRET_KEY, 'utf-8')
        message_bytes = bytes(message, 'utf-8')
        hmac_sha256 = hmac.new(keys, message_bytes, hashlib.sha256)
        expected_signature = base64.b64encode(hmac_sha256.digest()).decode('utf-8')
        
        if expected_signature != esewa_res.get("signature"):
            return HttpResponse("Payment verification failed: Signature mismatch", status=400)
            
        if esewa_res.get("status") != "COMPLETE":
            return HttpResponse("Payment not completed", status=400)
            
        # Extract user_id from transaction_uuid
        transaction_uuid = esewa_res.get("transaction_uuid", "")
        parts = transaction_uuid.split("-")
        if len(parts) < 2:
            return HttpResponse("Invalid transaction UUID format", status=400)
            
        user_id = parts[0]
            
        # Infer plan from amount
        amount_str = esewa_res.get("total_amount", "0").replace(',', '')
        amount = float(amount_str)
        
        selected_plan = None
        for p_key, p_val in PLANS.items():
            if p_key != "free" and float(p_val["price"]) == amount:
                selected_plan = p_key
                break
                
        if not selected_plan:
            return HttpResponse("Unknown payment amount", status=400)
            
        plan_config = PLANS[selected_plan]
        now = datetime.utcnow()
        end_date = now + timedelta(days=plan_config["duration_days"])
        
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "plan": selected_plan,
                    "subscription_type": "esewa",
                    "subscription_start": now,
                    "subscription_end": end_date,
                    "updated_at": now
                }
            }
        )
        
        frontend_url = f"{FRONTEND_URL}/profile"
        
        html_response = f"""
        <html>
            <head><title>Payment Successful</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: green;">Payment Successful (Demo)</h1>
                <p>Your subscription has been successfully upgraded to {plan_config['name']}!</p>
                <a href="{frontend_url}" style="display: inline-block; padding: 10px 20px; background-color: #007BFF; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px;">Return to Dashboard</a>
            </body>
        </html>
        """
        
        return HttpResponse(html_response)
        
    except Exception as e:
        return HttpResponse(f"Error handling success: {str(e)}", status=500)

@csrf_exempt
def payment_failure(request):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
    
    frontend_url = f"{FRONTEND_URL}/subscription"
    
    html_response = f"""
    <html>
        <head><title>Payment Failed</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1 style="color: red;">Payment Failed or Cancelled</h1>
            <p>Your payment could not be processed. No charges were made.</p>
            <a href="{frontend_url}" style="display: inline-block; padding: 10px 20px; background-color: #6c757d; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px;">Return to Subscriptions</a>
        </body>
    </html>
    """
    
    return HttpResponse(html_response)
