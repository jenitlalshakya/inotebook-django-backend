import jwt
from django.http import JsonResponse
from django.conf import settings
from functools import wraps
from core.mongo import users_collection

JWT_SECRET = settings.JWT_SECRET

def jwt_required(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JsonResponse({"error": "Authorization header missing"}, status=401)

        try:
            # Expect header: "Bearer <token>"
            token = auth_header.split(" ")[1]
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            request.user_id = payload["user_id"]
        except Exception:
            return JsonResponse({"error": "Invalid or expired token"}, status=401)
        
        return func(request, *args, **kwargs)
    
    return wrapper
