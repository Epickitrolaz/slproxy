"""
Metrics and Live Request Logger
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import time
from collections import deque


class RequestLog(BaseModel):
    id: str
    timestamp: float = Field(default_factory=time.time)
    client_ip: str = ""
    api_key_id: Optional[str] = None
    endpoint: str = ""
    model: str = ""
    provider_id: str = ""
    account_id: str = ""
    status_code: int = 200
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    is_stream: bool = False
    error: Optional[str] = None


class MetricsManager:
    def __init__(self, max_recent_logs: int = 500):
        self.max_recent_logs = max_recent_logs
        self.recent_logs: deque[RequestLog] = deque(maxlen=max_recent_logs)
        self.total_requests: int = 0
        self.total_errors: int = 0
        self.total_tokens: int = 0
        self.provider_stats: Dict[str, Dict[str, Any]] = {}

    def record_request(self, log: RequestLog):
        self.recent_logs.appendleft(log)
        self.total_requests += 1
        if log.status_code >= 400:
            self.total_errors += 1
        self.total_tokens += log.total_tokens
        
        p = log.provider_id or "unknown"
        if p not in self.provider_stats:
            self.provider_stats[p] = {
                "requests": 0,
                "errors": 0,
                "tokens": 0,
                "total_latency_ms": 0.0,
            }
        self.provider_stats[p]["requests"] += 1
        if log.status_code >= 400:
            self.provider_stats[p]["errors"] += 1
        self.provider_stats[p]["tokens"] += log.total_tokens
        self.provider_stats[p]["total_latency_ms"] += log.latency_ms

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "total_tokens": self.total_tokens,
            "success_rate": (
                (self.total_requests - self.total_errors) / self.total_requests
                if self.total_requests > 0
                else 1.0
            ),
            "provider_stats": self.provider_stats,
        }

    def get_recent_logs(self, limit: int = 50) -> List[RequestLog]:
        return list(self.recent_logs)[:limit]
