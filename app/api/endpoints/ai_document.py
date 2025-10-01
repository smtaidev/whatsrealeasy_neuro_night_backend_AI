# app/api/endpoints/ai_document.py


from pydantic import BaseModel, Field
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, logger
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
from app.db.database_connection import get_database
from app.api.models.ai_document import KnowledgeBaseFileResponse
from fastapi.responses import JSONResponse
from app.core.config import settings
import httpx


def now_utc():
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


router = APIRouter(prefix="/service-knowledge", tags=["service Knowledge Base"])


@router.post("/knowledge-base/file", response_model=KnowledgeBaseFileResponse)
async def create_knowledge_base_file(
    file: UploadFile = File(...),
    serviceId: str = Form(..., description="MongoDB ObjectId of the service"),
    db=Depends(get_database),
):

    # Validate serviceId
    if not serviceId:
        raise HTTPException(status_code=400, detail="serviceId is required")
    try:
        if not ObjectId.is_valid(serviceId):
            raise HTTPException(status_code=400, detail="Invalid serviceId format. Must be a 24-character hexadecimal string.")
        service = await db.services.find_one({"_id": ObjectId(serviceId)})
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid serviceId format. Must be a 24-character hexadecimal string.")
    
    if not service:
        raise HTTPException(status_code=404, detail="service not found")


    knowledgeBaseExists = await db.AiknowledgeBase.find_one({"serviceId":ObjectId(serviceId)})
    # print(f"\n knowledge base existence check: {knowledgeBaseExists}\n")

    if knowledgeBaseExists is not None:
        # print(f"\n knowledge base for this {knowledgeBaseExists.get("serviceId")} already exists. Deleting the previous one\n")
        await db.AiknowledgeBase.delete_one({"serviceId": ObjectId(serviceId)})
        delete_knowledge_base_file(knowledgeBaseExists.get("knowledgeBaseId"))
    
    service_name = service.get("serviceName")
    name = service_name + " Knowledge Base"

    # Upload file to ElevenLabs API
    API_KEY = settings.ELEVENLABS_API_KEY
    url = "https://api.elevenlabs.io/v1/convai/knowledge-base/file"

    files = {"file": (file.filename, await file.read())}
    data = {"name": name}
    headers = {"xi-api-key": API_KEY}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, files=files, data=data)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to upload to ElevenLabs")
        kb_data = response.json()  # { "id": ..., "name": ... }

    # Prepare KB record for MongoDB
    kb_record = {
        "serviceId": ObjectId(serviceId),
        "knowledgeBaseId": kb_data["id"],
        "knowledgeBaseName": kb_data["name"],
        "fileName": file.filename,
        "createdAt": now_utc(),
        "updatedAt": now_utc(),
    }

    # Save into MongoDB
    await db.AiknowledgeBase.insert_one(kb_record)

    # Return in response model format
    return {
        "knowledgeBaseId": kb_data["id"],
        "knowledgeBaseName": kb_data["name"],
    }

@router.delete("/knowledge-base/{knowledge_base_id}")
async def delete_knowledge_base_file(
    knowledge_base_id: str,
    db=Depends(get_database)
):
    """
    Delete a knowledge base by its knowledgeBaseId.
    Steps:
    1️⃣ Delete from MongoDB.
    2️⃣ Delete from ElevenLabs API.
    3️⃣ Return JSON response with KB info.
    """

    # Find the KB document in MongoDB
    kb_doc = await db.AiknowledgeBase.find_one({"knowledgeBaseId": knowledge_base_id})
    if not kb_doc:
        raise HTTPException(status_code=404, detail="Knowledge base document not found")

    service_id = kb_doc.get("serviceId")
    knowledge_base_name = kb_doc.get("knowledgeBaseName")
    file_name = kb_doc.get("fileName")

    # 1️⃣ Delete from MongoDB first
    delete_result = await db.AiknowledgeBase.delete_one({"knowledgeBaseId": knowledge_base_id})
    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=500, detail="Failed to delete KB document from database")

    # 2️⃣ Delete from ElevenLabs API (optional failure should not block DB deletion)
    try:
        API_KEY = settings.ELEVENLABS_API_KEY
        url = f"https://api.elevenlabs.io/v1/convai/knowledge-base/{knowledge_base_id}"
        async with httpx.AsyncClient() as client:
            response = await client.delete(url, headers={"xi-api-key": API_KEY})
            # ElevenLabs may return 200 or 204 for success
            if response.status_code not in [200, 204]:
                # Log warning, but don't fail the request
                logger.info(f"Warning: ElevenLabs delete failed: {response.status_code} {response.text}")
    except Exception as e:
        logger.info(f"Warning: Exception when deleting from ElevenLabs: {e}")

    # 3️⃣ Return JSON response
    return JSONResponse(
        status_code=200,
        content={
            "message": "Knowledge base document deleted successfully",
            "serviceId": service_id,
            "knowledgeBaseId": knowledge_base_id,
            "knowledgeBaseName": knowledge_base_name,
            "fileName": file_name,
            "deletedAt": now_utc().isoformat()
        }
    )


@router.get("/knowledge-base/{service_id}")
async def get_knowledge_base_list(
    service_id: str,
    db=Depends(get_database)
):
    """
    Get all knowledge base documents for a specific service.
    Returns a list of knowledge base files with their metadata.
    """

    # Find all KB documents for the service
    kb_docs = await db.AiknowledgeBase.find({"serviceId": service_id}).to_list(length=1000)
    
    if not kb_docs:
        return JSONResponse(
            status_code=200,
            content={
                "message": "No knowledge base documents found for this service",
                "serviceId": service_id,
                "knowledgeBaseList": []
            }
        )

    # Format response
    knowledge_base_list = []
    for kb in kb_docs:
        knowledge_base_list.append({
            "knowledgeBaseId": kb.get("knowledgeBaseId"),
            "knowledgeBaseName": kb.get("knowledgeBaseName"),
            "fileName": kb.get("fileName"),
            "createdAt": kb.get("createdAt").isoformat() if kb.get("createdAt") else None,
            "updatedAt": kb.get("updatedAt").isoformat() if kb.get("updatedAt") else None
        })

    return JSONResponse(
        status_code=200,
        content={
            "serviceId": service_id,
            "knowledgeBaseList": knowledge_base_list
        }
    )


