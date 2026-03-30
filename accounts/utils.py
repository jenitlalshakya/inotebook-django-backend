import jwt
from django.http import JsonResponse
from django.conf import settings
from functools import wraps
from bson import ObjectId
from core.mongo import users_collection
from datetime import datetime

JWT_SECRET = settings.JWT_SECRET

def jwt_required(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        auth_header = request.headers.get("Authorization")
        token = request.GET.get("token")

        if not auth_header and not token:
            return JsonResponse({"success": False, "error": "Authorization header or token missing"}, status=401)

        try:
            if auth_header:
                # Validate header format
                parts = auth_header.split(" ")
                if len(parts) != 2 or parts[0] != "Bearer":
                    return JsonResponse({"success": False, "error": "Invalid authorization format"}, status=401)
                token = parts[1]

            # Decode token
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])

            user_id = payload.get("user_id")
            token_iat = payload.get("iat")

            if not user_id:
                return JsonResponse({"success": False, "error": "Invalid token payload"}, status=401)

            # Fetch user
            user = users_collection.find_one({"_id": ObjectId(user_id)})

            if not user:
                return JsonResponse({"success": False, "error": "User not found"}, status=404)

            # Check subscription expiry
            plan = user.get("plan", "free")
            if plan != "free":
                sub_end = user.get("subscription_end")
                if sub_end:
                    if isinstance(sub_end, str):
                        try:
                            sub_end = datetime.fromisoformat(sub_end)
                        except ValueError:
                            pass
                    if isinstance(sub_end, datetime) and datetime.utcnow() > sub_end:
                        # Expired, revert to free
                        users_collection.update_one(
                            {"_id": ObjectId(user_id)},
                            {
                                "$set": {"plan": "free"},
                                "$unset": {"subscription_type": "", "subscription_start": "", "subscription_end": ""}
                            }
                        )
                        plan = "free"
                        user["plan"] = "free"

            # 🔐 Check if password was changed after token was issued
            if user.get("password_changed_at") and token_iat:
                password_changed_time = user["password_changed_at"]

                # Convert token_iat (timestamp) to datetime if needed
                if isinstance(token_iat, (int, float)):
                    token_iat = datetime.utcfromtimestamp(token_iat)

                if token_iat < password_changed_time:
                    return JsonResponse({"success": False, "error": "Token expired due to password change. Please login again."}, status=401)

            # Attach user_id and plan info to request
            request.user_id = user_id
            request.plan = plan
            request.storage_used = user.get("storage_used", 0)

        except jwt.ExpiredSignatureError:
            return JsonResponse({"success": False, "error": "Token expired"}, status=401)

        except jwt.InvalidTokenError:
            return JsonResponse({"success": False, "error": "Invalid token"}, status=401)

        except Exception:
            return JsonResponse({"success": False, "error": "Authentication failed"}, status=401)

        return func(request, *args, **kwargs)

    return wrapper
