# app/api/endpoints/connect_ai_agent_with_twilio.py


from fastapi import APIRouter, Depends, HTTPException
import httpx
from pydantic import BaseModel
import requests
from app.api.models.ai_agent_model import PhoneAssignment
from app.core.config import settings
from app.db.database_connection import get_database

router = APIRouter(prefix="/ai-call-routing", tags=["AI Call Routing"])

# Config
ELEVENLABS_API_KEY = settings.ELEVENLABS_API_KEY
TWILIO_ACCOUNT_SID = settings.TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN = settings.TWILIO_AUTH_TOKEN
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/convai"


@router.post("/assign-phone-to-ai-agent")
async def assign_phone_to_agent(assignment: PhoneAssignment, db=Depends(get_database)):

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        
        if assignment.call_type == "inbound":
            # Step 1: Import the Twilio phone number
            payload = {
                "phone_number": assignment.twilio_phone_number,
                "label": assignment.label,
                "sid": TWILIO_ACCOUNT_SID,
                "token": TWILIO_AUTH_TOKEN,
                "supports_outbound": False
            }
        
        elif assignment.call_type == "outbound":
            # Step 1: Import the Twilio phone number
            payload = {
                "phone_number": assignment.twilio_phone_number,
                "label": assignment.label,
                "sid": TWILIO_ACCOUNT_SID,
                "token": TWILIO_AUTH_TOKEN,
                # "supports_outbound": True,
                "supports_inbound": False
            }

        # Step 1: Import the Twilio phone number
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ELEVENLABS_API_URL}/phone-numbers",
                json=payload,
                headers=headers
            )

            if response.status_code not in (200, 201):
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to import phone number: {response.text}"
                )

            phone_data = response.json()
            phone_number_id = phone_data.get("phone_number_id")
            if not phone_number_id:
                raise HTTPException(status_code=500, detail="No phone_number_id returned from ElevenLabs")

            # Step 2: Assign the imported number to an agent
            update_payload = {"agent_id": assignment.agent_id}
            update_resp = requests.patch(
                f"{ELEVENLABS_API_URL}/phone-numbers/{phone_number_id}",
                json=update_payload,
                headers=headers
            )

            if update_resp.status_code not in (200, 201):
                raise HTTPException(
                    status_code=update_resp.status_code,
                    detail=f"Failed to assign agent: {update_resp.text}"
                )

            # save the phone number id to the service document
            phoneIdSaved = await db.services.update_one(
                {"phoneNumber": assignment.twilio_phone_number},
                {
                    "$set": {
                        "phone_number_id": phone_number_id
                    }
                }
            )

            
            return {
                "message": f"Successfully assigned {assignment.twilio_phone_number} to agent {assignment.agent_id}",
                "phone_number_id": phone_number_id,
                "elevenlabs_import": phone_data,
                "elevenlabs_update": update_resp.json()
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


