import json
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from core.mongo import notes_collection
from core.schema.Note_Schema import NoteSchema
from core.utils.encryption import encrypt_text, decrypt_text
from accounts.utils import jwt_required
from bson import ObjectId

@csrf_exempt
@jwt_required
def create_note(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST method required"}, status=405)

    try:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid JSON body"}, status=400)
            
        # Validate input
        validated = NoteSchema(**data)

        enc_title = encrypt_text(validated.title)
        enc_content = encrypt_text(validated.content)
        enc_tag = encrypt_text(validated.tag)

        # Create note dictionary
        note = {
            "user_id": ObjectId(request.user_id),
            "title": enc_title,
            "content": enc_content,
            "tag": enc_tag,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        result = notes_collection.insert_one(note)

        return JsonResponse({"success": True, "note_id": str(result.inserted_id)}, status=201)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@jwt_required
def get_notes(request):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "GET method required"}, status=405)

    try:
        try:
            limit = min(max(int(request.GET.get("limit", 20)), 1), 100)
            skip = max(int(request.GET.get("skip", 0)), 0)
        except ValueError:
            return JsonResponse({"success": False, "error": "Invalid pagination values"}, status=400)

        notes = notes_collection.find({"user_id": ObjectId(request.user_id)}).sort("updated_at", -1)\
                    .skip(skip)\
                    .limit(limit)

        note_list = []

        for note in notes:
            note_list.append({
                "id": str(note["_id"]),
                "title": decrypt_text(note["title"]),
                "content": decrypt_text(note["content"]),
                "tag": decrypt_text(note["tag"]),
                "created_at": note["created_at"].isoformat() + "Z",
                "updated_at": note["updated_at"].isoformat() + "Z"
            })

        return JsonResponse({"success": True, "notes": note_list}, status=200)
    
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@jwt_required
def search_notes(request):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "GET method required"}, status=405)

    try:
        search = request.GET.get("q", "").strip()
        try:
            limit = min(max(int(request.GET.get("limit", 20)), 1), 100)
            skip = max(int(request.GET.get("skip", 0)), 0)
        except ValueError:
            return JsonResponse({"success": False, "error": "Invalid pagination values"}, status=400)

        if not search:
            return JsonResponse({"success": True, "notes": []}, status=200)

        user_id = request.user_id
        # 1. Fetch all user notes (no regex – fields are encrypted in DB)
        notes_cursor = notes_collection.find({"user_id": ObjectId(user_id)}).sort("updated_at", -1)
        notes_list = list(notes_cursor)

        # 2. Decrypt in memory (never stored back to DB)
        decrypted_notes = []
        for note in notes_list:
            decrypted_notes.append({
                "id": str(note["_id"]),
                "title": decrypt_text(note["title"]),
                "content": decrypt_text(note["content"]),
                "tag": decrypt_text(note["tag"]),
                "created_at": note["created_at"].isoformat() + "Z",
                "updated_at": note["updated_at"].isoformat() + "Z"
            })

        # 3. Parse multiple conditions (comma-separated); each is field:keyword or general keyword
        conditions = [c.strip() for c in search.split(",") if c.strip()]

        title_filters = []
        content_filters = []
        tag_filters = []
        general_filters = []

        for cond in conditions:
            if cond.startswith("title:"):
                kw = cond.replace("title:", "", 1).strip().lower()
                if kw:
                    title_filters.append(kw)
            elif cond.startswith("content:"):
                kw = cond.replace("content:", "", 1).strip().lower()
                if kw:
                    content_filters.append(kw)
            elif cond.startswith("tag:"):
                kw = cond.replace("tag:", "", 1).strip().lower()
                if kw:
                    tag_filters.append(kw)
            else:
                kw = cond.lower()
                if kw:
                    general_filters.append(kw)

        # 4. Filter:
        #    - Within a given field, ANY of its filters may match (OR logic).
        #    - Between different fields, ALL present field groups must match (AND logic).
        #    - General (no-prefix) keywords keep existing behavior: ALL of them must match somewhere.
        if not (title_filters or content_filters or tag_filters or general_filters):
            filtered = []
        else:
            filtered = []
            for note in decrypted_notes:
                title_val = (note.get("title") or "").lower()
                content_val = (note.get("content") or "").lower()
                tag_val = (note.get("tag") or "").lower()

                # AND between fields: if a field group has filters, it must match at least one (OR within field)
                if title_filters and not any(kw in title_val for kw in title_filters):
                    continue
                if content_filters and not any(kw in content_val for kw in content_filters):
                    continue
                if tag_filters and not any(kw in tag_val for kw in tag_filters):
                    continue

                # General (no-prefix) terms: preserve original semantics (ALL must match somewhere)
                general_ok = True
                for kw in general_filters:
                    if kw not in title_val and kw not in content_val and kw not in tag_val:
                        general_ok = False
                        break

                if not general_ok:
                    continue

                filtered.append(note)

        # 5. Paginate after filtering
        results = filtered[skip : skip + limit]

        return JsonResponse({"success": True, "notes": results}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@jwt_required
def update_note(request, note_id):
    if request.method != "PUT":
        return JsonResponse({"success": False, "error": "PUT method required"}, status=405)

    try:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid JSON body"}, status=400)

        update_data = {}

        if "title" in data:
            enc_title = encrypt_text(data["title"])
            update_data["title"] = enc_title

        if "content" in data:
            enc_content = encrypt_text(data["content"])
            update_data["content"] = enc_content

        if "tag" in data:
            enc_tag = encrypt_text(data["tag"])
            update_data["tag"] = enc_tag

        update_data["updated_at"] = datetime.utcnow()

        result = notes_collection.update_one(
            {
                "_id": ObjectId(note_id),
                "user_id": ObjectId(request.user_id)
            },
            {"$set": update_data}
        )

        if result.matched_count == 0:
            return JsonResponse({"success": False, "error": "Note not found"}, status=404)
        
        return JsonResponse({"success": True, "message": "Note updated successfully"}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@csrf_exempt
@jwt_required
def delete_note(request, note_id):
    if request.method != "DELETE":
        return JsonResponse({"success": False, "error": "DELETE method required"}, status=405)

    try:
        result = notes_collection.delete_one(
            {
                "_id": ObjectId(note_id),
                "user_id": ObjectId(request.user_id)
            }
        )

        if result.deleted_count == 0:
            return JsonResponse({"success": False, "error": "Note not found"}, status=404)

        return JsonResponse({"success": True, "message": "Note deleted successfully"}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)
