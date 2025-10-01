#app/models/ai_agent_model.py

from pydantic import BaseModel, Field
from beanie import Document, Link, PydanticObjectId
from typing import List, Optional
from datetime import datetime, timezone
from enum import Enum
from bson import ObjectId

# Enum for Call Status
class CallStatus(Enum):
    INITIATED = "initiated"
    RINGING = "ringing"
    IN_PROGRESS = "in-progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BUSY = "busy"
    NO_ANSWER = "no-answer"
    CANCELED = "canceled"

# Enum for Direction (Used for both Twilio and Eleven Labs)
class Direction(Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class KnowledgeBaseModel(BaseModel):
    id: str  # Maps to AiknowledgeBase.knowledgeBaseId
    name: str  # Maps to AiknowledgeBase.knowledgeBaseName

class AgentCreateRequest(BaseModel):
    first_message: Optional[str] = None
    max_duration_seconds: Optional[int] = None
    stability: Optional[float] = None
    speed: Optional[float] = None
    similarity_boost: Optional[float] = None
    llm: Optional[str] = None
    temperature: Optional[float] = None
    daily_limit: Optional[int] = None

class AgentUpdateRequest(BaseModel):
    first_message: Optional[str] = None
    max_duration_seconds: Optional[int] = None
    stability: Optional[float] = None
    speed: Optional[float] = None
    similarity_boost: Optional[float] = None
    llm: Optional[str] = None
    temperature: Optional[float] = None
    daily_limit: Optional[int] = None

class serviceResponse(BaseModel):
    id: str
    service_name: str
    knowledge_base_name: str = ""
    knowledge_base_Id: str = ""
    phone_number: str
    voice_id: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class AgentDataResponse(BaseModel):
    first_message: Optional[str] = None
    max_duration_seconds: Optional[int] = None
    stability: Optional[float] = None
    speed: Optional[float] = None
    similarity_boost: Optional[float] = None
    llm: Optional[str] = None
    temperature: Optional[float] = None
    daily_limit: Optional[int] = None


# TimestampedModel for common timestamp fields
class TimestampedModel(BaseModel):
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AICallWebhookPayload(BaseModel):
    agent_id: str
    agent_name: Optional[str] = None
    conversation_id: Optional[str] = None
    start_time_unix_secs: Optional[int] = None
    call_duration_secs: Optional[int] = None
    message_count: Optional[int] = None
    status: Optional[CallStatus] = None
    call_successful: Optional[bool] = None
    direction: Optional[Direction] = None


# AIAgent Model
class AIAgent(Document,TimestampedModel):
    callType: str
    agentId: str
    first_message: str
    serviceId: ObjectId 
    
    class Settings:
        collection = "aiagents"

    class Config:
        arbitrary_types_allowed = True  # Allow arbitrary types like ObjectId


# AICallLog Model for Eleven Labs
class AICallLog(TimestampedModel, Document):  # Changed to Document
    id: PydanticObjectId = Field(default=None, alias="_id")
    call_sid: str = Field(..., description="Twilio CallSid")
    serviceId: Optional[PydanticObjectId] = None
    agent_id: str  
    conversation_id: Optional[str] = None
    from_number: str
    to_number: str
    callType: Direction
    call_status: CallStatus
    call_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    call_started_at: Optional[datetime] = None
    call_completed_at: Optional[datetime] = None
    call_duration: Optional[int] = None
    # recording_url: Optional[str] = None
    recording_duration: Optional[int] = None
    call_transcript: Optional[str] = None
    # recording_sid: Optional[str] = None 
    name : Optional[str] = None
    contact_number :Optional[str] = None
    company :Optional[str] = None
    email: Optional[str] = None

    meeting_time :Optional[str] = None
    area :Optional[str] = None
    description: Optional[str] = None

    class Settings:
        collection = "AICallLog"  

# Request model
class PhoneAssignment(BaseModel):
    twilio_phone_number: str
    call_type: str
    agent_id: str
    label: str = "Support Line"  # optional friendly label

class Tools(BaseModel):
    tool_id: str
    name: str
    description: str

    class Settings:
        collection = "tools"
    