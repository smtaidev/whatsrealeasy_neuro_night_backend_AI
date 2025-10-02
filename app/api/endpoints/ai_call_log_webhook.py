#app/api/endpoints/ai_call_log_webhook.py

from fastapi import APIRouter, Request, HTTPException, logger
import httpx
import hmac
import hashlib
import time
from bson import ObjectId
from fastapi.responses import JSONResponse, StreamingResponse
import os
import json
import requests
import io

from app.core.config import settings
from app.api.models.ai_agent_model import AICallLog, CallStatus, Direction
from datetime import datetime, timezone, timedelta
from app.services.shared_state import get_shared_state

router = APIRouter(prefix="/webhook", tags=["Eleven labs web hooks"])

# Load the shared secret from environment variable or config
ELEVENLABS_WEBHOOK_SECRET = settings.ELEVENLABS_WEBHOOK
ELEVENLABS_API_KEY = settings.ELEVENLABS_API_KEY  # You must have this
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"

# Tolerance in seconds for how old timestamp can be (to prevent replay)
TIMESTAMP_TOLERANCE = 30 * 60  # e.g. 30 minutes



# -------------------------------------------------
# 1️⃣ INITIATION WEBHOOK – store initial call info
# -------------------------------------------------
@router.post("/initiation-webhook")
async def initiation_webhook(request: Request):
    """
    Called at call start. Creates a record in MongoDB with temp_id.
    """
    shared_state = get_shared_state(request.app)
    body = await request.json()
    # print("initialize webhook data", body)

    caller_id = body.get("caller_id", "")
    agent_id = body.get("agent_id", "")
    called_number = body.get("called_number", "")
    call_sid = body.get("call_sid", "")  # may be empty at initiation

    # Generate a temporary ID for this record (use ObjectId)
    temp_id = str(ObjectId())
    service = await shared_state.db_manager.db.services.find_one({"phoneNumber":caller_id})
    if service is not None:
        direction = Direction.OUTGOING
    else:
        service = await shared_state.db_manager.db.services.find_one({"phoneNumber":called_number})
        direction = Direction.INCOMING


    # Insert initial record in DB
    call_doc = AICallLog(
        _id=ObjectId(temp_id),
        call_sid=call_sid,  # may be empty initially
        agent_id=agent_id,
        from_number=caller_id,
        to_number=called_number,
        callType=direction,
        serviceId = service.get("_id"),
        call_status=CallStatus.INITIATED,
        call_time=datetime.now(timezone.utc),
        call_started_at=datetime.now(timezone.utc),
    )
    await call_doc.insert()
    # print("Initial call record inserted:", call_doc.id)

    # Return dynamic variables for ElevenLabs
    dynamic_variables = {
        "temp_id": temp_id,
        "from_number": caller_id,
        "to_number": called_number,
        "call_sid": call_sid,
        "agent_id": agent_id,
    }

    return JSONResponse(
        {
            "type": "conversation_initiation_client_data",
            "dynamic_variables": dynamic_variables,
        }
    )


# -------------------------------------------------
# 2️⃣ POST–CALL WEBHOOK – update record
# -------------------------------------------------
@router.post("/elevenlabs-call-log")
async def handle_post_call_transcription(request: Request):
    """
    Post–call webhook from ElevenLabs.
    1. Verify signature
    2. Fetch conversation details
    3. Update our AICallLog using either temp_id (preferred) or twilio_sid
    """
    raw_body = await request.body()
    shared_state = get_shared_state(request.app)

    # ---------- 1. Verify signature ----------
    sig_header = request.headers.get("ElevenLabs-Signature") \
                 or request.headers.get("elevenlabs-signature")
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing signature header")

    try:
        parts = dict(item.split("=", 1) for item in sig_header.split(","))
        timestamp_str = parts["t"]
        signature_provided = parts["v0"]
        timestamp = int(timestamp_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid signature header")

    if abs(int(time.time()) - timestamp) > TIMESTAMP_TOLERANCE:
        raise HTTPException(status_code=400, detail="Timestamp too old")

    expected = hmac.new(
        ELEVENLABS_WEBHOOK_SECRET.encode(),
        f"{timestamp_str}.{raw_body.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature_provided, expected):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # ---------- 2. Parse ElevenLabs payload ----------
    body = json.loads(raw_body)
    data = body.get("data", {})
    
    # print(f"\n\n conversation data elevenlabs: {data} \n\n")



    conversation_id = data.get("conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id missing")

    # Fetch full conversation
    convo_url = f"{ELEVENLABS_BASE_URL}/v1/convai/conversations/{conversation_id}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(convo_url, headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        })
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to fetch conversation")
    convo = resp.json()

    # print(f"\n\n conversation response from elevenlabs: {convo} \n\n")


    # ---------- 3. Extract fields ----------
    client_data = convo.get("conversation_initiation_client_data", {}) or {}
    dynamic_vars = client_data.get("dynamic_variables", {}) or {}
    lead_data = convo.get("analysis",{}) or {}
    specific_lead_data = lead_data.get("data_collection_results",{}) or {}

    # print(f"\n\n specific_lead_data: {specific_lead_data} \n\n")

    name = specific_lead_data.get("name", {}).get("value", None)
    contact_number = specific_lead_data.get("contact_number", {}).get("value", None)
    company = specific_lead_data.get("company", {}).get("value", None)
    email = specific_lead_data.get("email", {}).get("value", None)
    meeting_time = specific_lead_data.get("meeting_time", {}).get("value", None)
    area = specific_lead_data.get("area", {}).get("value", None)
    description = lead_data.get("transcript_summary",{}) or {}

    # print(f"\n\nemail: {email}\n\n")

    temp_id         = dynamic_vars.get("temp_id")
    twilio_sid      = dynamic_vars.get("call_sid") or dynamic_vars.get("system__call_sid") or ""
    conversation_id = dynamic_vars.get("system__conversation_id") or conversation_id
    agent_id        = dynamic_vars.get("agent_id") or dynamic_vars.get("system__agent_id")
    from_number   = dynamic_vars.get("from_number") or dynamic_vars.get("system__caller_id") or ""
    to_number     = dynamic_vars.get("to_number") or dynamic_vars.get("system__called_number") or ""
    status_full   = convo.get("status") or data.get("status")
    transcript    = "\n".join(
        f"{t.get('role')}: {t.get('message')}" for t in convo.get("transcript", [])
    )

    start_unix    = convo.get("metadata", {}).get("start_time_unix_secs")
    duration_sec  = convo.get("metadata", {}).get("call_duration_secs")
    started_at    = datetime.fromtimestamp(start_unix, timezone.utc) if start_unix else None
    completed_at  = (datetime.fromtimestamp(start_unix + duration_sec, timezone.utc)
                     if start_unix and duration_sec else None)
    

    # #---------- Find service ----------
    service = await shared_state.db_manager.db.services.find_one({"phoneNumber":from_number})
    if service is not None:
        serviceId = service.get("_id")
    else:
        service = await shared_state.db_manager.db.services.find_one({"phoneNumber":to_number})
        serviceId = service.get("_id")


    # ---------- 4. Find call record ----------
    call_log = None
    if temp_id:  # preferred lookup
        call_log = await AICallLog.find_one({"_id": ObjectId(temp_id)})
    if not call_log and twilio_sid:
        call_log = await AICallLog.find_one({"call_sid": twilio_sid})

    if not call_log:
        raise HTTPException(
            status_code=404,
            detail="No matching call log found using temp_id or call_sid"
        )

    # ---------- 5. Update ----------
    try:
        call_status = CallStatus(status_full)
    except Exception:
        call_status = CallStatus.COMPLETED


    await call_log.set({
        AICallLog.serviceId: serviceId,
        AICallLog.agent_id:           agent_id,
        AICallLog.conversation_id:    conversation_id,
        AICallLog.from_number:       from_number or call_log.from_number,
        AICallLog.to_number:         to_number   or call_log.to_number,
        AICallLog.call_status:       call_status,
        AICallLog.call_started_at:   started_at or call_log.call_started_at,
        AICallLog.call_completed_at: completed_at,
        AICallLog.call_duration:     duration_sec,
        AICallLog.recording_duration: duration_sec,
        AICallLog.call_transcript:   transcript,
        AICallLog.call_sid:          twilio_sid or call_log.call_sid,
        AICallLog.name:             name,
        AICallLog.contact_number:   contact_number,
        AICallLog.company:          company,
        AICallLog.email:            email,
        AICallLog.meeting_time:     meeting_time,
        AICallLog.area:             area,
        AICallLog.description:      description
    })

    saved_call_log = await shared_state.db_manager.db.AICallLog.find_one({"call_sid":twilio_sid or call_log.call_sid})
    # print(f"\n\n saved call log {saved_call_log}\n\n")

    if meeting_time is not None:
    
        if isinstance(meeting_time, str):
            meeting_time_obj = datetime.fromisoformat(meeting_time)
        else:
            meeting_time_obj = meeting_time

        # Now you can safely calculate end time
        end_time = meeting_time_obj + timedelta(hours=1)

        async with httpx.AsyncClient() as client:
            meeting_set_url =f"https://api.advanceaimarketing.cloud/api/v1/appointments"
            # meeting_time_obj = datetime.fromisoformat(meeting_time)
            response = await client.post(
                meeting_set_url,
                json={
                    "callLogId": str(saved_call_log.get("_id")),
                    "summary": f"Meeting with Advance {service.get('serviceName')} marketing CEO Keith Sundstrom",
                    "description": description,
                    "start": {
                        "dateTime": meeting_time_obj.isoformat(),
                        "timeZone": "America/Los_Angeles"
                    },
                    "end": {
                        "dateTime": end_time.isoformat(),
                        "timeZone": "America/Los_Angeles"
                    }
                }
            )
            # print(f"\n\n response for calendar hit : {response.json()}\n\n")

            if response.status_code != 200:
                # print(f"\n\nFailed to link meeting to google calendar: {response.text}\n\n")
                raise HTTPException(status_code=500, detail=f"Failed to link agent to service: {response.text}")





    # print("✅ ElevenLabs post-call update:", call_log.id)
    return {
        "status": "updated",
        "conversation_id": conversation_id,
        "call_sid": twilio_sid,
        "temp_id": temp_id,
    }


@router.get("/elevenlabs/conversation/{conversation_id}/audio")
def get_conversation_audio(conversation_id: str):
    url = f"https://api.elevenlabs.io/v1/convai/conversations/{conversation_id}/audio"
    headers = {"xi-api-key": ELEVENLABS_API_KEY}

    response = requests.get(url, headers=headers, stream=True)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch conversation audio")

    audio_bytes = io.BytesIO(response.content)
    return StreamingResponse(audio_bytes, media_type="audio/mpeg", headers={
        "Content-Disposition": f"attachment; filename={conversation_id}.mp3"
    })
