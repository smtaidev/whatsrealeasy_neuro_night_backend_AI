# app/api/endpoints/ai_agent.py


from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from typing import Optional, List
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError
import logging
from app.services.elevenlabs import create_eleven_agent, update_eleven_agent, get_agent_data
from app.db.database_connection import get_database
from bson import ObjectId
from datetime import datetime, timezone
from app.services.prompt import generate_elevenlabs_prompt
from app.api.models.ai_agent_model import AIAgent, AgentCreateRequest, AgentUpdateRequest, KnowledgeBaseModel, serviceResponse
from app.core.config import settings
from app.api.models.ai_document import KnowledgeBaseFileResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services", tags=["services"])

ELEVENLABS_API_KEY = settings.ELEVENLABS_API_KEY
ELEVENLABS_BASE_URL_VOICE = "https://api.elevenlabs.io/v1/voices"

def now_utc():
    return datetime.now(timezone.utc)

@router.post("/create-service/")
async def create_service(
    serviceName: str,
    phoneNumber:str,
    db=Depends(get_database)
):
    check_phone_number = await db.services.find_one({"phoneNumber":phoneNumber})
    if check_phone_number is not None:
        return JSONResponse(
        status_code=200,
        content={
            "message": f"service already exists with that phone number {phoneNumber}"
        }
    )

    try:
        headers = {"xi-api-key": ELEVENLABS_API_KEY}

        # --- Call ElevenLabs API ---
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{ELEVENLABS_BASE_URL_VOICE}/{settings.VOICE_ID}",
                headers=headers
            )

        if response.status_code != 200:
            return JSONResponse(
                status_code=response.status_code,
                content={"error": True, "message": response.text}
            )

        elevenlabs_data = response.json()
        voice_name = elevenlabs_data.get("name") or elevenlabs_data.get("name")
        if not voice_name:
            return JSONResponse(
                status_code=500,
                content={"error": True, "message": "ElevenLabs response missing name"}
            )

        # --- Save metadata to service collection ---
        db_record = {
            "serviceName": serviceName,
            "voiceId": settings.VOICE_ID,
            "voiceName": voice_name,
            "phoneNumber": phoneNumber,
            "requires_verification": False,
            "createdAt": now_utc(),
            "updatedAt": now_utc()
        }

        result = await db.services.insert_one(db_record)
        db_record["_id"] = str(result.inserted_id)
        db_record["createdAt"] = db_record["createdAt"].isoformat()
        db_record["updatedAt"] = db_record["updatedAt"].isoformat()

        # --- Return response ---
        return JSONResponse(
            status_code=200,
            content={
                "message": "service created successfully with agent voice",
                "db_record": db_record,
                "elevenlabs_response": elevenlabs_data
            }
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": True, "message": str(e)}
        )
    
@router.patch("/update-service/")
async def update_service(
    service_id: str,
    serviceName: str = Body(None),
    phoneNumber: str = Body(None),
    db=Depends(get_database)
):
    # Find the service
    check_service = await db.services.find_one({"_id": ObjectId(service_id)})
    if check_service is None:
        return JSONResponse(
            status_code=404,
            content={"message": "Service not found"}
        )

    update_fields = {}
    if serviceName:
        update_fields["serviceName"] = serviceName
    if phoneNumber:
        update_fields["phoneNumber"] = phoneNumber

    if not update_fields:
        return JSONResponse(
            status_code=400,
            content={"message": "No fields provided for update"}
        )

    update_fields["updatedAt"] = now_utc()

    # Perform update
    await db.services.update_one(
        {"_id": ObjectId(service_id)},
        {"$set": update_fields}
    )

    # Fetch the updated record
    updated_record = await db.services.find_one({"_id": ObjectId(service_id)})
    updated_record["_id"] = str(updated_record["_id"])
    updated_record["createdAt"] = updated_record["createdAt"].isoformat()
    updated_record["updatedAt"] = updated_record["updatedAt"].isoformat()

    return JSONResponse(
        status_code=200,
        content={
            "message": "Service updated successfully",
            "db_record": updated_record
        }
    )

    

# ----------------------------
# Helper: Fetch service by ID
# ----------------------------
@router.get("/{service_id}", response_model=serviceResponse)
async def get_services_by_id(service_id: str, db=Depends(get_database)) -> serviceResponse:
    # --- Validate service_id ---
    try:
        oid = ObjectId(service_id)
    except Exception:
        logger.error(f"Invalid service_id: {service_id}")
        raise HTTPException(status_code=400, detail="Invalid service_id")

    # --- Fetch service data ---
    service_data = await db.services.find_one({"_id": oid})
    if not service_data:
        raise HTTPException(status_code=404, detail="service not found")

    knowledgeBase = await db.AiknowledgeBase.find_one({"serviceId":ObjectId(service_id)})
    # print(f"\n\n service knowledgebase: {knowledgeBase}\n\n")
    # --- Build Response ---
    return serviceResponse(
        id=str(service_data["_id"]),
        service_name=service_data.get("serviceName", ""),
        knowledge_base_name = knowledgeBase.get("knowledgeBaseName",""),
        knowledge_base_Id = knowledgeBase.get("knowledgeBaseId",""),
        phone_number = service_data.get("phoneNumber",""),
        voice_id=service_data.get("voiceId", ""),
        created_at = service_data.get("createdAt"),
        updated_at = service_data.get("updatedAt")
    )

# ----------------------------
# Build ElevenLabs Payload
# ----------------------------
def build_elevenlabs_payload(
    service: serviceResponse,
    tool_ids: List[str],
    first_message: Optional[str] = None,
    prompt: str = None,
    max_duration_seconds: Optional[int] = None,
    stability: Optional[float] = None,
    speed: Optional[float] = None,
    similarity_boost: Optional[float] = None,
    llm: Optional[str] = None,
    temperature: Optional[float] = None,
    daily_limit: Optional[int] = None
) -> dict:

    # Defaults
    stability = stability if stability is not None else 0.5
    speed = speed if speed is not None else 1.0
    similarity_boost = similarity_boost if similarity_boost is not None else 0.8
    max_duration_seconds = max_duration_seconds if max_duration_seconds is not None else 600
    llm = llm if llm is not None else "gemini-2.0-flash-lite"
    temperature = temperature if temperature is not None else 0
    daily_limit = daily_limit if daily_limit is not None else 100000
    
    # Filter knowledge bases correctly
    kb_payload = []
    if service.knowledge_base_Id and service.knowledge_base_name:
        kb_payload = [
            {
                "id": service.knowledge_base_Id,
                "name": service.knowledge_base_name,
                "type": "file"
            }
        ]
        
    payload = {
        "conversation_config": {
            "asr": {
                "quality": "high",
                "provider": "elevenlabs",
                "user_input_audio_format": "ulaw_8000"
            },
            "turn": {
                "turn_timeout": 2.5,
                "silence_end_call_timeout": -1
            },
            "tts": {
                "voice_id": service.voice_id if service.voice_id else "cjVigY5qzO86Huf0OWal",
                "agent_output_audio_format": "ulaw_8000",
                "optimize_streaming_latency": 3,
                "stability": stability,
                "speed": speed,
                "similarity_boost": similarity_boost
            },
            "conversation": {
                "text_only": False,
                "max_duration_seconds": max_duration_seconds,
                "client_events": [
                    "audio",
                    "interruption",
                    "user_transcript",
                    "agent_response",
                    "agent_response_correction"
                ]
            },
            "agent": {
                "first_message": first_message or "Hello, how can I assist you today?",
                "language": "en",
                "prompt": {
                    "prompt": prompt,
                    "llm": llm,
                    "temperature": temperature,
                    "max_tokens": -1,
                    "knowledge_base": kb_payload,
                    "tool_ids": tool_ids,
                    "built_in_tools": {
                        "end_call": {
                            "name": "end_call",
                            "description": "Ends the call",
                            "params": {
                                "system_tool_type": "end_call",
                                "disable_interruptions": False,
                                "force_pre_tool_speech": False
                            }
                        },
                        "language_detection": {
                            "name": "language_detection",
                            "description": "Detects the language spoken by the user",
                            "params": {
                                "system_tool_type": "language_detection",
                                "disable_interruptions": False,
                                "force_pre_tool_speech": False
                            }
                        },
                    }
                },
                "rag": {
                    "enabled": True,
                    "embedding_model": "multilingual_e5_large_instruct",
                    "max_vector_distance": 0.6,
                    "max_documents_length": 50000,
                    "max_retrieved_rag_chunks_count": 20
                }
            }
        },
        "platform_settings": {
            "overrides": {
                "enable_conversation_initiation_client_data_from_webhook": True,
                "conversation_config_override": {
                    "conversation": {
                        "text_only": False
                    },
                },
            },
            "data_collection": {
                "name": {
                    "type": "string",
                    "description": "the person name"
                },
                "contact_number": {
                    "type": "string",
                    "description": "the phone number of the person"
                },
                "area": {
                    "type": "string",
                    "description": "from which area the person called from"
                },
                "email": {
                    "type": "string",
                    "description": "ask for the email of the person. Intelligently format the email with '@' and email extensions"
                },
                "company": {
                    "type": "string",
                    "description": "for which company the person wants the service"
                },
                "meeting_time": {
                    "type": "string",
                    "description": "when the person has fixed the meeting time finally.Catch the time according to PST timezone and return data in datetime format"
                }
            },
            "call_limits": {
                "agent_concurrency_limit": -1,
                "daily_limit": daily_limit,
                "bursting_enabled": True
            },
            "workspace_overrides": {
                "webhooks": {
                    "post_call_webhook_id": "6aabaf49cdb5455dae69bf765f4d156b"
                }
            }
        },
        "name": f"{service.service_name} AI Agent"
    }

    return payload


# ----------------------------
# Endpoint: Create Agent
# ----------------------------
@router.post("/create-agent/")
async def create_agent(
    call_type: str,
    service_id: str,
    req: AgentCreateRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):

    # Validate service
    logger.info(f"Creating AI agent for service_id: {service_id}")
    service = await get_services_by_id(service_id, db)
    if not service:
        logger.error(f"service not found: {service_id}")
        raise HTTPException(status_code=404, detail=f"service not found: {service_id}")
    


    # Fetch only tool_id fields from the collection
    tool_docs = await db.tools.find({}, {"tool_id": 1, "_id": 0}).to_list(length=None)

    # Extract tool_id values into a list
    tool_ids = [doc["tool_id"] for doc in tool_docs if "tool_id" in doc]

    # logger.info(f"\n\n tool id's: {tool_ids}\n\n")

    agentExists = await db.aiagents.find_one({"serviceId":ObjectId(service_id)})


    if agentExists is not None:
        # print(f"\n Agent Already Exists for this {service_id}  updating this {agentExists.get("agentId")} agent")
        await update_agent(service_id, agentExists.get("agentId"), req.max_duration_seconds, req.first_message,db )

        return {
            "status": "success",
            "agent": "agent updated successfully",
            "service_link": "No service link for updated agent"
        }

    # Generate ElevenLabs prompt
    prompt = generate_elevenlabs_prompt(
        agent_name=f"{service.service_name} Call Center Agent",
        service_name=service.service_name,
        callback_timeframe="30 minutes"
    )

    # Build ElevenLabs payload
    try:
        payload = build_elevenlabs_payload(
            service,
            tool_ids = tool_ids,
            prompt=prompt,
            first_message=req.first_message,
            max_duration_seconds=req.max_duration_seconds,
            stability=req.stability,
            speed=req.speed,
            similarity_boost=req.similarity_boost,
            llm=req.llm,
            temperature=req.temperature,
            daily_limit=req.daily_limit
        )
        logger.debug(f"ElevenLabs payload: {payload}")
    except ValueError as e:
        logger.error(f"Payload build failed for service_id {service_id}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid payload: {str(e)}")

    # Call ElevenLabs service
    agent_response = await create_eleven_agent(payload)
    # print(f"\n\n elevenlabs response:{agent_response}\n\n")

    agentId = agent_response.get("agent_id")
    
    if not agentId:
        # print(f"\n\n elevenlabs response:{agent_response}\n\n")
        return agent_response.json()
        # logger.error(f"Agent creation failed for service_id {service_id}: no agentId returned")
        # raise HTTPException(status_code=500, detail="Agent creation failed, no agentId returned.")


    # Create AI agent document
    ai_agent = AIAgent(
        callType =call_type,
        first_message =req.first_message,
        agentId=agentId,
        serviceId=ObjectId(service_id),
    )

    # Insert into aiagents collection
    try:
        result = await db.aiagents.insert_one(ai_agent.model_dump(exclude={"id"}))
        logger.info(f"AI agent created successfully for service_id {service_id}, agentId: {agentId}, inserted_id: {str(result.inserted_id)}")
    except DuplicateKeyError:
        logger.error(f"Duplicate key error for serviceId: {service_id}")
        raise HTTPException(status_code=409, detail="AI agent creation failed due to duplicate serviceId")
    except Exception as e:
        logger.error(f"Failed to create AI agent for service_id {service_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create AI agent: {str(e)}")


    # Link agent with service
    service_phone = service.phone_number
    label = f"{service.service_name} AI Agent connection"

    async with httpx.AsyncClient() as client:
        service_api_url = f"{settings.WEBHOOK_URL}/ai-call-routing/assign-phone-to-ai-agent"
        response = await client.post(
            service_api_url,
            json={
                "twilio_phone_number": service_phone,
                "call_type":call_type,
                "agent_id": agentId,
                "label": label
            }
        )

        if response.status_code != 200:
            logger.error(f"Failed to link agent to service, most probably the number has not been bought from you twilio account: {response.text}")
            raise HTTPException(status_code=500, detail=f"Failed to link agent to twilio, most probably the number has not been bought from you twilio account: {response.text}")

    logger.info(f"Linked AI agent {agentId} to service {service_id}")

    return {
        "status": "success",
        "agent": agent_response,
        "service_link": response.json()
    }

async def update_agent(
    serviceId:str,
    agentId:str,
    callDuration:int,
    firstMessage:str,
    db
):
    
    knowledgeBase= await db.AiknowledgeBase.find_one({"serviceId":ObjectId(serviceId)})
    knowledgeBaseId=knowledgeBase.get("knowledgeBaseId")
    knowledgeBaseName = knowledgeBase.get("knowledgeBaseName")
    
    kb_payload = [
        {
            "id": knowledgeBaseId,
            "name": knowledgeBaseName,
            "type": "file"
        }
    ]

    conversation_payload_part={}
    agent_payload_part = {}
    prompt_payload_part = {}

    conversation_payload_part["max_duration_seconds"] = callDuration
    agent_payload_part["first_message"] = firstMessage
    prompt_payload_part["knowledge_base"]=kb_payload
    
    if prompt_payload_part:
        agent_payload_part["prompt"] = prompt_payload_part

    final_payload = {
        "conversation_config": {
            "conversation": conversation_payload_part,
            "agent": agent_payload_part
        }
    }

    try:
        update_response = await update_eleven_agent(agentId, final_payload)
        logger.info(f"Successfully PATCHED agent {agentId} at ElevenLabs.")
    except httpx.HTTPStatusError as e:
        logger.error(f"Failed to PATCH ElevenLabs agent {agentId}: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to update agent at external service: {e.response.text}")

    await db.aiagents.update_one(
        {"agentId": agentId},
        {"$set": {"updatedAt": datetime.utcnow()}}
    )

    return {
        "status": "success",
        "message": f"Agent {agentId} was successfully updated.",
        "update_response": update_response
    }



# # ----------------------------
# # Endpoint: Get Agent Info
# # ----------------------------
# @router.get("/{service_id}/agents/{agentId}", response_model=AgentDataResponse)
# async def get_agent_info(service_id: str, agentId: str):
#     try:
#         data = await get_agent_data(agentId)
#     except httpx.HTTPStatusError as e:
#         raise HTTPException(status_code=e.response.status_code, detail=str(e))
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

#     # Extract the relevant fields
#     return {
#     "first_message": data.get("conversation_config", {}).get("agent", {}).get("first_message"),
#     "knowledge_base_ids": [
#         kb.get("id") for kb in data.get("conversation_config", {}).get("agent", {}).get("prompt", {}).get("knowledge_base", [])
#         if isinstance(kb, dict) and "id" in kb
#     ],
#     "max_duration_seconds": data.get("conversation_config", {}).get("conversation", {}).get("max_duration_seconds"),
#     "stability": data.get("conversation_config", {}).get("tts", {}).get("stability"),
#     "speed": data.get("conversation_config", {}).get("tts", {}).get("speed"),
#     "similarity_boost": data.get("conversation_config", {}).get("tts", {}).get("similarity_boost"),
#     "llm": data.get("conversation_config", {}).get("agent", {}).get("prompt", {}).get("llm"),
#     "temperature": data.get("conversation_config", {}).get("agent", {}).get("prompt", {}).get("temperature"),
#     "daily_limit": data.get("platform_settings", {}).get("call_limits", {}).get("daily_limit")
# }