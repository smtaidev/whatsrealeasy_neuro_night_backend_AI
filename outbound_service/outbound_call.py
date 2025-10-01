#outbound_service/outbound_call.py


import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import logging
import math
import pandas as pd

from bson import ObjectId
import httpx
from app.core.config import settings
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException,BackgroundTasks
from app.db.database_connection import get_database
from io import BytesIO, StringIO

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outbound", tags=["outbound-call"])

ELEVENLABS_API_KEY = settings.ELEVENLABS_API_KEY
ELEVENLABS_API_BATCH_CALL = "https://api.elevenlabs.io/v1/convai/batch-calling/submit"

headers = {
    "xi-api-key": ELEVENLABS_API_KEY,
    "Content-Type": "application/json"
}

def now_pacific():
    return datetime.now(ZoneInfo("America/Los_Angeles"))


batch_call_id = ""

@router.post("/start-batch-call/")
async def process_numbers(
    starting_time: int,
    call_duration: int,
    call_gap: int,
    total_numbers_in_each_batch: int,
    background_tasks: BackgroundTasks,
    numberfile: UploadFile = File(...),
    serviceId: str = Form(...),
    db=Depends(get_database)
):
    try:
        file_content = await numberfile.read()

        # Detect file type based on filename
        if numberfile.filename.endswith(".csv"):
            df = pd.read_csv(StringIO(file_content.decode("utf-8")))
        elif numberfile.filename.endswith((".xls", ".xlsx")):
            df = pd.read_excel(BytesIO(file_content))
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type. Only .csv, .xls and .xlsx are allowed.")
        
        df['phoneNumbers'] = df['phoneNumbers'].dropna().reset_index(drop=True)

        
    except Exception as e:
        logger.exception("Failed to parse file.")
        raise HTTPException(status_code=400, detail=f"File parsing error: {str(e)}")

    if 'phoneNumbers' not in df.columns:
        raise HTTPException(status_code=400, detail="Missing required column: 'phoneNumbers'")


    serviceId_obj = ObjectId(serviceId)

    # Look up related records
    agent = await db.aiagents.find_one({"serviceId": serviceId_obj})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found for given serviceId.")

    service = await db.services.find_one({"_id": serviceId_obj})
    if not service:
        raise HTTPException(status_code=404, detail="Service not found.")
    
    job_id = ObjectId()
    job_record = {
        "_id": job_id,
        "status": "pending",
        "total_numbers": len(df),
        "submitted_batches": 0,
        "completed": False,
        "start_time": now_pacific(),
        "end_time": None
    }
    await db.batch_jobs.insert_one(job_record)

    background_tasks.add_task(
        run_batch_job,
        df, total_numbers_in_each_batch, agent, service,
        starting_time, call_duration, call_gap, job_id, db
    )


    return {"message": "Batch job started in background.", "job_id": str(job_id)}

async def run_batch_job(df, batch_size, agent, service, starting_time, call_duration, call_gap, job_id, db):
    total_count = 0

    for i in range(0, len(df), batch_size):
        batch = df["phoneNumbers"].iloc[i:i + batch_size]
        recipients = [{"phone_number": f"+{str(phone).strip()}"} for phone in batch]
        total_count += len(recipients)

        if not recipients:
            raise HTTPException(status_code=400, detail="No valid phone numbers found in the file.")

        payload = {
            "call_name": f"Batch Call {service.get('serviceName', '')} {now_pacific().isoformat()}",
            "agent_id": agent.get("agentId"),
            "agent_phone_number_id": service.get("phone_number_id", ""),
            "scheduled_time_unix": starting_time,
            "recipients": recipients
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                ELEVENLABS_API_BATCH_CALL,
                json=payload,
                headers=headers
            )

            batch_call_id = response.json().get("id")

            if response.status_code not in (200, 201):
                await db.batch_jobs.update_one({"_id": job_id}, {
                    "$set": {"status": "failed", "end_time": now_pacific()}
                })
                logger.error(f"Batch call failed: {response.text}")
                return

            await db.batch_jobs.update_one({"_id": job_id}, {
                "$inc": {"submitted_batches": 1}
            })

            await asyncio.sleep(call_duration + call_gap)

        await db.batch_jobs.update_one({"_id": job_id}, {
            "$set": {
                "status": "completed",
                "completed": True,
                "end_time": now_pacific()
            }
        })

        logger.info(f"Job {job_id} completed. {total_count} phone numbers processed.")


@router.get("/batch-job-status/")
async def get_batch_job_status(job_id: str, db=Depends(get_database)):
    try:
        job = await db.batch_jobs.find_one({"_id": ObjectId(job_id)})
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        return {
            "status": job["status"],
            "total_numbers": job["total_numbers"],
            "submitted_batches": job["submitted_batches"],
            "start_time": job["start_time"],
            "end_time": job["end_time"],
            "completed": job["completed"]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cancell-batch-call")
async def cancell_batch_call():

    url = f"https://api.elevenlabs.io/v1/convai/batch-calling/{batch_call_id}/cancel"
    headers={
        "xi-api-key": ELEVENLABS_API_KEY
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers)

        print(f"Status code: {resp.status_code}")
        print(f"Response text: {resp.text}")
        return resp.json()
    

    # return response.json()


    # url = "https://api.elevenlabs.io/v1/convai/agents/create"
    # headers = {
    #     "xi-api-key": ELEVEN_API_KEY,
    #     "Content-Type": "application/json"
    # }

    # print(f"Sending POST to {url} with payload: {payload}")
    # print(f"Headers: {headers}")

    # async with httpx.AsyncClient() as client:
    #     resp = await client.post(url, headers=headers, json=payload)

    #     print(f"Status code: {resp.status_code}")
    #     print(f"Response text: {resp.text}")
    #     return resp.json()
    