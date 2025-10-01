# app/core/database_manager.py
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING
from pymongo.errors import OperationFailure
from bson import ObjectId
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, mongodb_url: str):
        self.mongodb_url = mongodb_url
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
    
    async def initialize(self):
        """Initialize MongoDB connection with proper configuration"""
        try:
            self.client = AsyncIOMotorClient(
                self.mongodb_url,
                maxPoolSize=50,
                minPoolSize=10,
                maxIdleTimeMS=30000,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=20000
            )
            
            # Get database name from URL
            db_name = settings.MONGO_DB_NAME
            self.db = self.client[db_name]
            
            # Test connection
            await self.client.admin.command('ping')
            logger.info("MongoDB connection established successfully")
            
            # Ensure indexes
            await self.ensure_indexes()
            
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB: {e}")
            raise
    
    async def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
    
    async def ensure_indexes(self):
        """Ensure database indexes exist - creates them if they don't exist"""
        try:
            # Services collection indexes
            try:
                await self.db.services.create_index([("phoneNumber", ASCENDING)], background=True)
                await self.db.services.create_index([("serviceName", ASCENDING)], background=True)
            except OperationFailure as e:
                logger.warning(f"Services index creation issue (may already exist): {e}")
            
            # AI agents collection indexes
            try:
                await self.db.aiagents.create_index([("serviceId", ASCENDING)], background=True)
                await self.db.aiagents.create_index([("agentId", ASCENDING)], background=True)
            except OperationFailure as e:
                logger.warning(f"AI agents index creation issue (may already exist): {e}")
            
            # Knowledge base collection indexes
            try:
                await self.db.AiknowledgeBase.create_index([("serviceId", ASCENDING)], background=True)
                await self.db.AiknowledgeBase.create_index([("knowledgeBaseId", ASCENDING)], background=True)
            except OperationFailure as e:
                logger.warning(f"Knowledge base index creation issue (may already exist): {e}")
            
            # Call log collection indexes
            try:
                await self.db.AICallLog.create_index([("call_sid", ASCENDING)], background=True)
                await self.db.AICallLog.create_index([("agent_id", ASCENDING)], background=True)
                await self.db.AICallLog.create_index([("serviceId", ASCENDING)], background=True)
            except OperationFailure as e:
                logger.warning(f"Call log index creation issue (may already exist): {e}")
            
            # Batch jobs collection indexes (for outbound service)
            try:
                await self.db.batch_jobs.create_index([("status", ASCENDING)], background=True)
                await self.db.batch_jobs.create_index([("start_time", ASCENDING)], background=True)
            except OperationFailure as e:
                logger.warning(f"Batch jobs index creation issue (may already exist): {e}")
            
            # Tools collection indexes
            try:
                await self.db.tools.create_index([("tool_id", ASCENDING)], background=True)
            except OperationFailure as e:
                logger.warning(f"Tools index creation issue (may already exist): {e}")
            
            logger.info("Database indexes ensured successfully")
            
        except Exception as e:
            logger.error(f"Failed to ensure indexes: {e}")
            # Don't raise - allow app to continue even if indexes fail