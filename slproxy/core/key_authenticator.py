"""
Key Authenticator Contract & Stub
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import time


class ApiKey(BaseModel):
    id: str
    key: str  # e.g. "slp-live-..."
    name: str
    created_at: float = Field(default_factory=time.time)
    expires_at: Optional[float] = None  # None = never expires
    max_requests: Optional[int] = None
    max_tokens: Optional[int] = None
    used_requests: int = 0
    used_tokens: int = 0
    is_active: bool = True
    allowed_plugins: List[str] = Field(default_factory=list)  # empty = all allowed
    allowed_models: List[str] = Field(default_factory=list)   # empty = all allowed
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)


class KeyAuthenticator:
    """
    Validates incoming request API keys against expiration,
    request limits, token limits, and model/provider restrictions.
    """
    def __init__(self):
        pass

    async def authenticate(self, auth_header: Optional[str], requested_model: str = "", plugin_id: str = "") -> ApiKey:
        raise NotImplementedError

    async def record_usage(self, key_id: str, requests_inc: int = 1, tokens_inc: int = 0):
        raise NotImplementedError
