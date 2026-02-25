import os
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client("inotebook_db")

users_collection = db["users"]
notes_collection = db["notes"]

users_collection.create_index([("email", ASCENDING)], unique=True)
