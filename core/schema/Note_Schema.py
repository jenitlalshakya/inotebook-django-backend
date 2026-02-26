from typing import Optional
from pydantic import BaseModel
from datetime import datetime

class NoteSchema(BaseModel):
    title: str
    content: str
    tag: Optional[str] = None
