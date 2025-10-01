#app/services/shared_state.py

from typing import Optional
from fastapi import HTTPException

class SharedState:
    """Shared state container for application-wide managers"""
    def __init__(self):
        self.redis_manager = None
        self.db_manager = None
        self.websocket_manager = None
        self.twilio_client = None
        self.health_status = None

def get_shared_state(app) -> SharedState:
    """Get shared state from FastAPI app"""
    if not hasattr(app.state, 'shared_state'):
        raise HTTPException(
            status_code=500, 
            detail="Application not properly initialized"
        )
    return app.state.shared_state

