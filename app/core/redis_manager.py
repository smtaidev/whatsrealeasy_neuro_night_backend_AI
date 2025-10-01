#app/core/redis_manager.py
import redis.asyncio as redis
import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub = None
        
    async def initialize(self):
        """Initialize Redis connection with proper configuration"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30,
                max_connections=50
            )
            
            # Test connection
            await self.redis_client.ping()
            logger.info("Redis connection established successfully")
            
            # Initialize pub/sub
            self.pubsub = self.redis_client.pubsub()
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            raise
    
    async def close(self):
        """Close Redis connections"""
        if self.pubsub:
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()
    
    def _prepare_redis_data(self, data: dict) -> dict:
        """Prepare data for Redis storage by converting None values to empty strings"""
        processed_data = {}
        for k, v in data.items():
            if v is None:
                processed_data[k] = ""  # Convert None to empty string
            else:
                processed_data[k] = v
        return processed_data
    


