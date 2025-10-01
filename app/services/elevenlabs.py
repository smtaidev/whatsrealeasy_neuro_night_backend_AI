#app/services/elevenlabs.py

import httpx
import os
from app.core.config import settings
ELEVEN_API_KEY = settings.ELEVENLABS_API_KEY

async def create_eleven_agent(payload: dict):
    url = "https://api.elevenlabs.io/v1/convai/agents/create"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json"
    }

    # print(f"Sending POST to {url} with payload: {payload}")
    # print(f"Headers: {headers}")

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)

        print(f"Status code: {resp.status_code}")
        print(f"Response text: {resp.text}")
        return resp.json()





async def update_eleven_agent(agent_id: str, partial_payload: dict) -> dict:

    if not ELEVEN_API_KEY:
        raise ValueError("ELEVENLABS_API_KEY is not set in environment variables.")

    headers = {
        "Content-Type": "application/json",
        "xi-api-key": ELEVEN_API_KEY
    }
    update_url = f"https://api.elevenlabs.io/v1/convai/agents/{agent_id}"

    async with httpx.AsyncClient() as client:
        response = await client.patch(update_url, headers=headers, json=partial_payload, timeout=30.0)
        # Raise an exception for bad status codes (4xx or 5xx)
        response.raise_for_status()
        return response.json()
    
async def get_agent_data(agent_id: str)->dict:
    if not ELEVEN_API_KEY:
        raise ValueError("ELEVENLABS_API_KEY is not set in enironment variables.")
    headers = {
        "Content-Type":"application/json",
        "xi-api-key": ELEVEN_API_KEY
    }
    updated_url = f"https://api.elevenlabs.io/v1/convai/agents/{agent_id}"

    async with httpx.AsyncClient() as client:
        response = await client.get(updated_url, headers=headers)
        response.raise_for_status()
        return response.json()
