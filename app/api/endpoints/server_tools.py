#app/api/endpoints/server_tools.py

import logging
from fastapi import APIRouter, Depends, Request, HTTPException, logger
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
from datetime import datetime
from zoneinfo import ZoneInfo
from app.db.database_connection import get_database
from app.services.shared_state import get_shared_state
from app.api.models.ai_agent_model import Tools


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["Tools web hooks"])

# Load the shared secret from environment variable or config
ELEVENLABS_API_KEY = settings.ELEVENLABS_API_KEY
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1/convai/tools"

# Tolerance in seconds for how old timestamp can be (to prevent replay)
TIMESTAMP_TOLERANCE = 30 * 60  # e.g. 30 minutes

@router.get("/booked-time")
async def get_meeting_time(db=Depends(get_database)):

    meeting_times = await db.AICallLog.find({}, {"meeting_time": 1, "_id": 0}).to_list(length=None)
    logger.info(f"\n\nbooked times are {meeting_times}\n\n")

    return meeting_times


@router.get("/get-current-time")
async def get_current_time():
    timezone = "America/Los_Angeles"
    now = datetime.now(ZoneInfo(timezone))
    logger.info(f"\n\nThe get current tool is hit, time: {now}\n\n")

    return {
        "datetime": now.isoformat(),
        "timezone": timezone,
        "display": now.strftime("%A, %B %d, %Y at %I:%M %p")
    }



@router.post("/create-tool")
async def create_tool(
    name: str,
    description: str,
    webhook_endpoint_name: str,
    db=Depends(get_database)
):
    # Create tool (POST /v1/convai/tools)
    response = requests.post(
        ELEVENLABS_BASE_URL,
        headers={
            "xi-api-key": ELEVENLABS_API_KEY
        },
        json={
            "tool_config": {
                "name": name,
                "description": description,
                "api_schema": {
                    "url": f"{settings.WEBHOOK_URL}/webhook/{webhook_endpoint_name}",
                    "method": "GET"
                },
                "type": "webhook"
            }
        },
    ).json()

    tool_id = response.get("id")

    tool_data = Tools(
        tool_id=tool_id,
        name=name,
        description=description
    )

    await db.tools.insert_one(tool_data.model_dump())

    return {
        "status": "success",
        "tool": response,
        "service_link": response
    }



