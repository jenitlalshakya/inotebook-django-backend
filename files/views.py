import re
import mimetypes
from datetime import datetime
from django.http import JsonResponse, StreamingHttpResponse
from urllib.parse import quote
from django.views.decorators.csrf import csrf_exempt
from bson import ObjectId
from core.mongo import files_collection, users_collection, fs
from accounts.utils import jwt_required
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

        # Sanitize filename
        safe_file_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', uploaded_file.name)

        # Store file in GridFS
        file_data = uploaded_file.read()
        gridfs_id = fs.put(
            file_data,
            filename=safe_file_name,
            content_type=uploaded_file.content_type or "application/octet-stream",
        )

        # Save record in DB
        file_record = {
            "user_id": ObjectId(request.user_id),
            "file_name": safe_file_name,
            "file_size": file_size,
            "file_type": uploaded_file.content_type,
            "gridfs_id": gridfs_id,
            "created_at": datetime.utcnow(),
        }

        result = files_collection.insert_one(file_record)

        # Update user storage
        users_collection.update_one(
            {"_id": ObjectId(request.user_id)},
            {"$inc": {"storage_used": file_size}},
        )

        return JsonResponse(
            {"success": True, "file_id": str(result.inserted_id)},
            status=201,
        )

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
        for f in files:
            file_list.append({
                "id": str(f["_id"]),
                "file_name": f.get("file_name", ""),
                "file_size": f.get("file_size", 0),
                "file_type": f.get("file_type", ""),
                "created_at": f.get("created_at").isoformat() + "Z" if f.get("created_at") else "",
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
        file_doc = files_collection.find_one(
            {"_id": ObjectId(file_id), "user_id": ObjectId(request.user_id)}
        )
        if not file_doc:
            return JsonResponse({"success": False, "error": "File not found"}, status=404)

        gridfs_id = file_doc.get("gridfs_id")
        if not gridfs_id:
            return JsonResponse({"success": False, "error": "File not stored in GridFS"}, status=404)

        try:
            grid_file = fs.get(gridfs_id)
        except Exception:
            return JsonResponse({"success": False, "error": "File data not found in GridFS"}, status=404)

        file_name = file_doc.get("file_name")
        content_type = (
            file_doc.get("file_type")
            or mimetypes.guess_type(file_name)[0]
            or "application/octet-stream"
        )

        def file_iterator():
            try:
                while True:
                    chunk = grid_file.read(8192)
                    if not chunk:
                        break
                    yield chunk
            finally:
                grid_file.close()

        response = StreamingHttpResponse(file_iterator(), content_type=content_type)
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(file_name)}"
        response["Content-Length"] = grid_file.length
        return response

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@jwt_required
def delete_file(request, file_id):
    if request.method != "DELETE":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        file_doc = files_collection.find_one(
            {"_id": ObjectId(file_id), "user_id": ObjectId(request.user_id)}
        )

        if not file_doc:
            return JsonResponse({"success": False, "error": "File not found"}, status=404)

        # Delete from GridFS
        gridfs_id = file_doc.get("gridfs_id")
        if gridfs_id:
            try:
                fs.delete(gridfs_id)
            except Exception:
                pass

        # Reduce storage
        file_size = file_doc.get("file_size", 0)
        users_collection.update_one(
            {"_id": ObjectId(request.user_id)},
            {"$inc": {"storage_used": -file_size}},
        )

        # Delete from DB
        files_collection.delete_one({"_id": ObjectId(file_id)})

        return JsonResponse({"success": True, "message": "File deleted successfully"}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)
