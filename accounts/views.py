import json
import jwt
from datetime import datetime
import bcrypt
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from core.mongo import users_collection
from core.schema.User_Schema import UserSchema
from django.conf import settings
from pymongo.errors import DuplicateKeyError

JWT_SECRET = settings.JWT_SECRET
PEPPER = settings.PEPPER

@csrf_exempt
def signup(request):
    if request.method == "POST":
        data = json.loads(request.body)

        # Get user data from body
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")

        password_to_hashed = password + PEPPER

        if not username or not email or not password:
            return JsonResponse({"error": "All fields are required"}, status=400)

        if users_collection.find_one({"email": email}):
            return JsonResponse({"error": "Email already exists"}, status=400)

        hashed_password = bcrypt.hashpw(password_to_hashed.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Create user object
        user = UserSchema(
            username=username,
            email=email,
            password=hashed_password,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Insert into Mongo
        try:
            users_collection.insert_one(user.dict())
        except DuplicateKeyError:
            return JsonResponse({"error": "Email already exists"}, status=400)

        return JsonResponse({"message": "User created successfully"})


@csrf_exempt
def login(request):
    if request.method == "POST":
        data = json.loads(request.body)

        email = data.get("email")
        password = data.get("password")

        password_to_check = password + PEPPER

        user = users_collection.find_one({"email": email})

        if not user:
            return JsonResponse({"error": "Invalid credentials"}, status=400)

        if not bcrypt.checkpw(password_to_check.encode("utf-8"), user["password"].encode("utf-8")):
            return JsonResponse({"error": "Invalid credentials"}, status=400)

        payload = {
            "user_id": str(user["_id"]),
            "exp": datetime.utcnow() + datetime.timedelta(days=1)
        }

        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

        return JsonResponse({"token": token})
