import json
import jwt
from datetime import datetime, timedelta
import bcrypt
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from core.mongo import users_collection, notes_collection
from core.schema.User_Schema import UserSchema
from django.conf import settings
from pymongo.errors import DuplicateKeyError
from .utils import jwt_required
from bson import ObjectId

JWT_SECRET = settings.JWT_SECRET
PEPPER = settings.PEPPER

@csrf_exempt
def signup(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            # Get user data from body
            name = data.get("name")
            email = data.get("email", "").strip().lower()
            password = data.get("password")

            password_to_hashed = password + PEPPER

            if not name or not email or not password:
                return JsonResponse({"success": False, "error": "All fields are required"}, status=400)

            if users_collection.find_one({"email": email}):
                return JsonResponse({"success": False, "error": "Email already exists"}, status=400)

            hashed_password = bcrypt.hashpw(password_to_hashed.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

            # Create user object
            user = UserSchema(
                name=name,
                email=email,
                password=hashed_password,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            # Insert into Mongo
            try:
                users_collection.insert_one(user.dict())
            except DuplicateKeyError:
                return JsonResponse({"success": False, "error": "Email already exists"}, status=400)

            return JsonResponse({"success": True, "message": "User created successfully"}, status=200)

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
def login(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            email = data.get("email", "").strip().lower()
            password = data.get("password")

            password_to_check = password + PEPPER

            user = users_collection.find_one({"email": email})

            if not user:
                return JsonResponse({"success": False, "error": "Invalid credentials"}, status=400)

            if not bcrypt.checkpw(password_to_check.encode("utf-8"), user["password"].encode("utf-8")):
                return JsonResponse({"success": False, "error": "Invalid credentials"}, status=400)

            payload = {
                "user_id": str(user["_id"]),
                "iat": datetime.utcnow(),   # issued at
                "exp": datetime.utcnow() + timedelta(days=1)
            }

            token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

            if isinstance(token, bytes):
                token = token.decode("utf-8")

            name = user.get("name", "")

            return JsonResponse({"success": True, "token": token, "name": name}, status=200)

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

@csrf_exempt
@jwt_required
def delete_account(request):
    if request.method == "DELETE":
        try:
            user_id = request.user_id
            result = users_collection.delete_one({"_id": ObjectId(user_id)})
            if result.deleted_count == 0:
                return JsonResponse({"success": False, "error": "User not found"}, status=404)

            notes_collection.delete_many({"user_id": ObjectId(user_id)})

            return JsonResponse({"success": True, "message": "Account and all related data deleted successfully"}, status=200)
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)
        
    return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
        
@csrf_exempt
@jwt_required
def change_password(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

        old_password = data.get("old_password")
        new_password = data.get("new_password")

        if not old_password or not new_password:
            return JsonResponse({"success": False, "error": "Both old and new password are required"}, status=400)

        if old_password == new_password:
            return JsonResponse({"success": False, "error": "Password must be different"}, status=400)

        # Get current user from JWT
        user = users_collection.find_one({"_id": ObjectId(request.user_id)})

        if not user:
            return JsonResponse({"success": False, "error": "User not found"}, status=404)
        
        # verify old password
        old_password_with_pepper = old_password + PEPPER

        if not bcrypt.checkpw(old_password_with_pepper.encode("utf-8"), user["password"].encode("utf-8")):
            return JsonResponse({"success": False, "error": "Password is incorrect"}, status=400)

        # Hash new password
        new_password_with_pepper = new_password + PEPPER
        hashed_new_password = bcrypt.hashpw(new_password_with_pepper.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Update Password in MongoDB
        users_collection.update_one(
            {"_id": ObjectId(request.user_id)},
            {
                "$set": {
                    "password": hashed_new_password,
                    "updated_at": datetime.utcnow(),
                    "password_changed_at": datetime.utcnow()
                }
            } 
        )

        return JsonResponse({"success": True, "message": "Password changed successfully"}, status=200)
    
    return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

@csrf_exempt
@jwt_required
def profile(request):
    if request.method == "GET":
        try:
            user = users_collection.find_one({"_id": ObjectId(request.user_id)})
            if not user:
                return JsonResponse({"success": False, "error": "User not found"}, status=404)

            created_at = user.get("created_at")
            created_at_str = None
            if created_at:
                if isinstance(created_at, datetime):
                    created_at_str = created_at.isoformat()
                else:
                    created_at_str = str(created_at)
            return JsonResponse({
                "success": True,
                "user": {
                    "name": user.get("name", ""),
                    "email": user.get("email", ""),
                    "created_at": created_at_str,
                }
            }, status=200)
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
