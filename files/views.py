import os
from datetime import datetime
from django.http import JsonResponse, FileResponse, Http404
from django.utils.encoding import smart_str
from django.views.decorators.csrf import csrf_exempt
from bson import ObjectId
from core.mongo import files_collection, users_collection
from core.schema.File_Schema import FileSchema
from accounts.utils import jwt_required
from django.conf import settings
from subscription.views import PLANS

@csrf_exempt
@jwt_required
def upload_file(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        if request.plan == "free":
            return JsonResponse({"success": False, "error": "File upload is not allowed on the free plan."}, status=403)

        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return JsonResponse({"success": False, "error": "No file uploaded"}, status=400)

        # Check storage limit
        plan_config = PLANS.get(request.plan, PLANS["free"])
        max_storage_bytes = plan_config["storage_limit_bytes"]
        file_size = uploaded_file.size
        
        if request.storage_used + file_size > max_storage_bytes:
            return JsonResponse({"success": False, "error": "Storage limit exceeded."}, status=403)

        # Ensure media dir exists
        user_dir = os.path.join(settings.MEDIA_ROOT, str(request.user_id))
        os.makedirs(user_dir, exist_ok=True)
        
        file_path = os.path.join(user_dir, uploaded_file.name)
        
        # Save file chunks
        with open(file_path, "wb+") as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)
                
        file_url = f"{settings.MEDIA_URL}{request.user_id}/{uploaded_file.name}"

        # Save record in db
        file_record = {
            "user_id": ObjectId(request.user_id),
            "file_name": uploaded_file.name,
            "file_size": file_size,
            "file_type": uploaded_file.content_type,
            "file_url": file_url,
            "created_at": datetime.utcnow()
        }
        
        # DB insert
        result = files_collection.insert_one(file_record)

        # Update user storage
        users_collection.update_one(
            {"_id": ObjectId(request.user_id)},
            {"$inc": {"storage_used": file_size}}
        )

        return JsonResponse({"success": True, "file_id": str(result.inserted_id), "file_url": file_url}, status=201)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@jwt_required
def list_files(request):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        files = files_collection.find({"user_id": ObjectId(request.user_id)}).sort("created_at", -1)
        file_list = []
        for file in files:
            file_list.append({
                "id": str(file["_id"]),
                "file_name": file.get("file_name", ""),
                "file_size": file.get("file_size", 0),
                "file_type": file.get("file_type", ""),
                "file_url": file.get("file_url", ""),
                "created_at": file.get("created_at").isoformat() + "Z" if file.get("created_at") else ""
            })

        return JsonResponse({"success": True, "files": file_list}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@csrf_exempt
@jwt_required
def download_file(request, file_id):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        # Fetch the file from DB
        file_doc = files_collection.find_one({"_id": ObjectId(file_id), "user_id": ObjectId(request.user_id)})
        if not file_doc:
            return JsonResponse({"success": False, "error": "File not found"}, status=404)

        file_name = file_doc.get("file_name")
        file_path = os.path.join(settings.MEDIA_ROOT, str(request.user_id), file_name)

        if not os.path.exists(file_path):
            return JsonResponse({"success": False, "error": "File missing from server"}, status=404)

        # Serve file as attachment
        response = FileResponse(open(file_path, "rb"), as_attachment=True)
        response['Content-Disposition'] = f'attachment; filename="{smart_str(file_name)}"'
        return response

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@csrf_exempt
@jwt_required
def delete_file(request, file_id):
    if request.method != "DELETE":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        file_doc = files_collection.find_one({"_id": ObjectId(file_id), "user_id": ObjectId(request.user_id)})
        
        if not file_doc:
            return JsonResponse({"success": False, "error": "File not found"}, status=404)

        # Delete from filesystem
        file_name = file_doc.get("file_name")
        file_path = os.path.join(settings.MEDIA_ROOT, str(request.user_id), file_name)
        if os.path.exists(file_path):
            os.remove(file_path)

        # Reduce storage
        file_size = file_doc.get("file_size", 0)
        users_collection.update_one(
            {"_id": ObjectId(request.user_id)},
            {"$inc": {"storage_used": -file_size}}
        )

        # Delete from DB
        files_collection.delete_one({"_id": ObjectId(file_id)})

        return JsonResponse({"success": True, "message": "File deleted successfully"}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)
