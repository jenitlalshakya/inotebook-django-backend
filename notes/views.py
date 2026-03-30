import json
import re
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
        
        # Enforce subscription limits
        if getattr(request, 'plan', 'free') == 'free':
            # Check note count
            total_notes = notes_collection.count_documents({
                "user_id": ObjectId(request.user_id),
                "is_deleted": {"$ne": True}
            })
            if total_notes >= 50:
                return JsonResponse({"success": False, "error": "Free plan limit reached (50 notes). Please upgrade your plan."}, status=403)
                
            # Check word count
            word_count = len(validated.content.split())
            if word_count > 500:
                return JsonResponse({"success": False, "error": f"Free plan limit exceeded: 500 words max per note (current: {word_count}). Please upgrade."}, status=403)

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

        query = {
                    "user_id": ObjectId(request.user_id),
                    "is_deleted": {"$ne": True},
                    "is_favorite": {"$ne": True}
                }

        total_count = notes_collection.count_documents(query)

        notes = notes_collection.find(query).sort("updated_at", -1)\
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

        return JsonResponse({"success": True, "count": total_count, "notes": note_list}, status=200)
    
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

        # 3. Parse multiple conditions (comma-separated); each is field:keyword or general keyword.
        #    Also support manual OR groups within a segment using "or", e.g. "title:db or content:db".
        conditions = [c.strip() for c in search.split(",") if c.strip()]

        title_filters = []
        content_filters = []
        tag_filters = []
        general_filters = []
        or_groups = []  # each group is a list of (field, keyword)

        for cond in conditions:
            # Detect manual OR groups between different fields: "... or ..."
            lower_cond = cond.lower()
            if " or " in lower_cond:
                parts = [p.strip() for p in re.split(r"\bor\b", cond, flags=re.IGNORECASE) if p.strip()]
                group = []
                for part in parts:
                    part_stripped = part.strip()
                    lower_part = part_stripped.lower()
                    if lower_part.startswith("title:"):
                        kw = part_stripped[len("title:"):].strip().lower()
                        if kw:
                            group.append(("title", kw))
                    elif lower_part.startswith("content:"):
                        kw = part_stripped[len("content:"):].strip().lower()
                        if kw:
                            group.append(("content", kw))
                    elif lower_part.startswith("tag:"):
                        kw = part_stripped[len("tag:"):].strip().lower()
                        if kw:
                            group.append(("tag", kw))
                    else:
                        kw = lower_part.strip()
                        if kw:
                            group.append(("general", kw))
                if group:
                    or_groups.append(group)
                continue

            # Normal single condition (no "or" inside segment)
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
        #    - OR groups: each group must have at least one matching condition.
        #    - General (no-prefix) keywords keep existing behavior: ALL of them must match somewhere.
        if not (title_filters or content_filters or tag_filters or general_filters or or_groups):
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

                # OR groups: each group must have at least one condition satisfied
                groups_ok = True
                for group in or_groups:
                    group_match = False
                    for field, kw in group:
                        if field == "title":
                            if kw in title_val:
                                group_match = True
                                break
                        elif field == "content":
                            if kw in content_val:
                                group_match = True
                                break
                        elif field == "tag":
                            if kw in tag_val:
                                group_match = True
                                break
                        elif field == "general":
                            if kw in title_val or kw in content_val or kw in tag_val:
                                group_match = True
                                break
                    if not group_match:
                        groups_ok = False
                        break

                if not groups_ok:
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
            # Enforce limit if free plan
            if getattr(request, 'plan', 'free') == 'free':
                word_count = len(data["content"].split())
                if word_count > 500:
                    return JsonResponse({"success": False, "error": f"Free plan limit exceeded: 500 words max per note (current: {word_count}). Please upgrade."}, status=403)
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
        result = notes_collection.update_one(
            {
                "_id": ObjectId(note_id),
                "user_id": ObjectId(request.user_id)
            },
            {
                "$set": {
                    "is_deleted": True,
                    "is_favorite": False
                },
            }
        )

        if result.matched_count == 0:
            return JsonResponse({"success": False, "error": "Note not found"}, status=404)

        return JsonResponse({"success": True, "message": "Note moved to Trash"}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@csrf_exempt
@jwt_required
def permanent_delete_note(request, note_id):
    if request.method != "DELETE":
        return JsonResponse({"success": False, "error": "DELETE method required"}, status=405)

    try:
        result = notes_collection.delete_one(
            {
                "_id": ObjectId(note_id),
                "user_id": ObjectId(request.user_id),
                "is_deleted": True
            }
        )

        if result.deleted_count == 0:
            return JsonResponse({"success": False, "error": "Note not found in trash"}, status=404)

        return JsonResponse({"success": True, "message": "Note permanently deleted"}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@csrf_exempt
@jwt_required
def empty_trash(request):
    if request.method != "DELETE":
        return JsonResponse({"success": False, "error": "DELETE method required"}, status=405)

    try:
        result = notes_collection.delete_many(
            {
                "user_id": ObjectId(request.user_id),
                "is_deleted": True
            }
        )

        return JsonResponse({"success": True, "message": f"{result.deleted_count} notes permanently deleted"}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@jwt_required
def get_trash_notes(request):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "GET method required"}, status=405)

    try:
        query = {"user_id": ObjectId(request.user_id), "is_deleted": True}

        notes = list(notes_collection.find(query).sort("updated_at", -1))

        note_list = []
        for note in notes:
            note_list.append({
                "id": str(note.get("_id")),
                "title": decrypt_text(note.get("title", "")),
                "content": decrypt_text(note.get("content", "")),
                "tag": decrypt_text(note.get("tag", "")),
                "created_at": note.get("created_at").isoformat() + "Z" if note.get("created_at") else "",
                "updated_at": note.get("updated_at").isoformat() + "Z" if note.get("updated_at") else ""
            })

        return JsonResponse({"success": True, "notes": note_list})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@csrf_exempt
@jwt_required
def restore_note(request, note_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST method required"}, status=405)

    try:
        # Find the note in trash
        result = notes_collection.update_one(
            {
                "_id": ObjectId(note_id),
                "user_id": ObjectId(request.user_id),
                "is_deleted": True
            },
            {"$set": {"is_deleted": False, "updated_at": datetime.utcnow()}}
        )

        if result.matched_count == 0:
            return JsonResponse({"success": False, "error": "Note not found in trash"}, status=404)

        # Fetch restored note to return
        note = notes_collection.find_one({"_id": ObjectId(note_id)})

        restored_note = {
            "id": str(note["_id"]),
            "title": decrypt_text(note.get("title", "")),
            "content": decrypt_text(note.get("content", "")),
            "tag": decrypt_text(note.get("tag", "")),
            "created_at": note.get("created_at").isoformat() + "Z" if note.get("created_at") else "",
            "updated_at": note.get("updated_at").isoformat() + "Z" if note.get("updated_at") else ""
        }

        return JsonResponse({"success": True, "note": restored_note}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)
        
@csrf_exempt
@jwt_required
def favorite_note(request, note_id):
    if request.method != "PUT":
        return JsonResponse({"success": False, "error": "PUT method required"}, status=405)

    try:
        result = notes_collection.update_one(
            {
                "_id": ObjectId(note_id),
                "user_id": ObjectId(request.user_id),
                "is_deleted": {"$ne": True}
            },
            {
                "$set": {"is_favorite": True}
            }
        )

        if result.matched_count == 0:
            return JsonResponse({"success": False, "error": "Note not found or unauthorized"}, status=404)

        return JsonResponse({"success": True, "is_favorite": True, "message": "Note marked as favorite"}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@csrf_exempt
@jwt_required
def unfavorite_note(request, note_id):
    if request.method != "PUT":
        return JsonResponse({"success": False, "error": "PUT method required"}, status=405)

    try:
        result = notes_collection.update_one(
            {
                "_id": ObjectId(note_id),
                "user_id": ObjectId(request.user_id),
                "is_deleted": {"$ne": True}
            },
            {
                "$set": {"is_favorite": False}
            }
        )

        if result.matched_count == 0:
            return JsonResponse({"success": False, "error": "Note not found or unauthorized"}, status=404)

        return JsonResponse({"success": True, "is_favorite": False, "message": "Note unfavorited"}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@jwt_required
def get_favorites(request):
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "GET method required"}, status=405)

    try:
        query = {
            "user_id": ObjectId(request.user_id),
            "is_favorite": True,
            "is_deleted": {"$ne": True}
        }

        notes = list(notes_collection.find(query).sort("updated_at", -1))

        note_list = []
        for note in notes:
            note_list.append({
                "id": str(note["_id"]),
                "title": decrypt_text(note.get("title", "")),
                "content": decrypt_text(note.get("content", "")),
                "tag": decrypt_text(note.get("tag", "")),
                "is_favorite": True,
                "created_at": note.get("created_at").isoformat() + "Z" if note.get("created_at") else "",
                "updated_at": note.get("updated_at").isoformat() + "Z" if note.get("updated_at") else ""
            })

        return JsonResponse({"success": True, "notes": note_list}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)
