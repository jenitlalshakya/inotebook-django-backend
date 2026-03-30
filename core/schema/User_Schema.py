from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class UserSchema(BaseModel):
    name: str
    email: EmailStr
    password: str
    plan: str = "free"
    subscription_type: Optional[str] = None
    subscription_start: Optional[datetime] = None
    subscription_end: Optional[datetime] = None
    storage_used: int = 0
    created_at: datetime
    updated_at: datetime