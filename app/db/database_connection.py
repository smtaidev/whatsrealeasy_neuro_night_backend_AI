# app/db/database_connection.py
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

client = AsyncIOMotorClient(str(settings.MONGODB_URL))
db = client[settings.MONGO_DB_NAME]

def get_database():
    return db
