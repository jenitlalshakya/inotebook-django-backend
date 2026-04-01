import os
from pymongo import MongoClient, ASCENDING, errors
import gridfs

MONGO_URI = os.getenv("MONGO_URI")

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    client.admin.command("ping")
    db = client["inotebook_db"]
    
    users_collection = db["users"]
    notes_collection = db["notes"]
    files_collection = db["files"]

    fs = gridfs.GridFS(db)

    users_collection.create_index([("email", ASCENDING)], unique=True)

except errors.ServerSelectionTimeoutError as e:
    raise RuntimeError(f"MongoDB connection failed: {e}") from e

except Exception as e:
    raise RuntimeError(f"MongoDB initialization failed: {e}") from e
