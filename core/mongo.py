import os
from pymongo import MongoClient, ASCENDING, errors

MONGO_URI = os.getenv("MONGO_URI")

try:
    # Connect with timeout
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    client.admin.command('ping')  # force a connection attempt
    db = client["inotebook_db"]

    # Collections
    users_collection = db["users"]
    notes_collection = db["notes"]

    # Ensure email uniqueness
    users_collection.create_index([("email", ASCENDING)], unique=True)

except errors.ServerSelectionTimeoutError as e:
    # SRV/TXT lookup failed or server unreachable
    raise RuntimeError(
        f"❌ MongoDB SRV/TXT lookup or connection failed: {e}\n"
        "Check DNS resolution or switch to standard URI for reliability."
    ) from e

except Exception as e:
    # Any other error
    raise RuntimeError(f"❌ MongoDB initialization failed: {e}") from e
    