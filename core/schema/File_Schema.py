from pydantic import BaseModel
from datetime import datetime
from bson import ObjectId

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema):
        return {
            "type": "string",
            "format": "objectid"
        }

class FileSchema(BaseModel):
    user_id: PyObjectId
    file_name: str
    file_size: int
    file_type: str
    file_url: str
    created_at: datetime
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }
