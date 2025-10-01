#app/core/config.py
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Twilio
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_API_KEY: str = os.getenv("TWILIO_API_KEY", "")
    TWILIO_API_SECRET: str = os.getenv("TWILIO_API_SECRET", "")
    TWILIO_APP_SID: str = os.getenv("TWILIO_APP_SID", "")

    # Elevenlabs
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY","")
    ELEVENLABS_WEBHOOK: str = os.getenv("ELEVENLABS_WEBHOOK","")
    VOICE_ID: str = os.getenv("VOICE_ID","")

    # Open AI Key
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Web hooks
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "") #ngrok url
    
    # Database
    MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017/")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "booking")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    MEETING_UPDATE_URL:str=os.getenv("meeting_update_url","")
    
    INSTANCE_ID: str = os.getenv("INSTANCE_ID", "instance-1")
    
    class Config:
        env_file = ".env"

settings = Settings()

