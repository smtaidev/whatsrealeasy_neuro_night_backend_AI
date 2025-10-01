#app/models/document.py

from pydantic import BaseModel, Field
from typing import Optional
from fastapi import UploadFile, File, Form

# Response Model
class KnowledgeBaseFileResponse(BaseModel):
    knowledgeBaseId: str = Field(..., description="The unique ID of the uploaded knowledge base document")
    knowledgeBaseName: str = Field(..., description="The name of the uploaded knowledge base document")
