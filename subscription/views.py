import json
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from bson import ObjectId
from core.mongo import users_collection
from accounts.utils import jwt_required

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
def payment_success(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        selected_plan = data.get("plan")
        
        if selected_plan not in ["pro_monthly", "pro_yearly"]:
            return JsonResponse({"success": False, "error": "Invalid plan"}, status=400)
            
        plan_config = PLANS[selected_plan]
        now = datetime.utcnow()
        end_date = now + timedelta(days=plan_config["duration_days"])
        
        users_collection.update_one(
            {"_id": ObjectId(request.user_id)},
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
        
        return JsonResponse({"success": True, "message": f"Successfully upgraded to {plan_config['name']}"}, status=200)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@csrf_exempt
@jwt_required
def payment_failure(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
    
    # We do nothing to the DB, just acknowledge the failure
    return JsonResponse({"success": True, "message": "Payment failed or cancelled."}, status=200)
