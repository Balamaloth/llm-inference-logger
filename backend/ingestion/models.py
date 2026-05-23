from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID

class InferenceLogRequest(BaseModel):
    """Incoming inference log from SDK"""
    request_id: str
    conversation_id: str
    session_id: str
    model: str
    provider: str
    status: str
    latency_ms: int
    input_tokens: Optional[int] = 0
    output_tokens: Optional[int] = 0
    total_tokens: Optional[int] = 0
    cost_usd: Optional[float] = 0.0
    error_message: Optional[str] = None
    request_preview: Optional[str] = None
    response_preview: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "request_id": "req-123",
                "conversation_id": "conv-456",
                "session_id": "sess-789",
                "model": "gpt-4",
                "provider": "openai",
                "status": "success",
                "latency_ms": 2340,
                "input_tokens": 25,
                "output_tokens": 150,
                "total_tokens": 175,
                "request_preview": "What is...",
                "response_preview": "The answer is...",
                "metadata": {"temperature": 0.7}
            }
        }

class MessageRequest(BaseModel):
    """Create a message"""
    role: str
    content: str
    tokens_estimated: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

class ConversationCreate(BaseModel):
    """Create a conversation"""
    user_id: str
    title: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class ConversationUpdate(BaseModel):
    """Update a conversation"""
    title: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class ConversationResponse(BaseModel):
    """Conversation response"""
    id: UUID
    user_id: str
    title: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    class Config:
        from_attributes = True

class MessageResponse(BaseModel):
    """Message response"""
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True

class InferenceLogResponse(BaseModel):
    """Inference log response"""
    id: UUID
    conversation_id: UUID
    model: str
    provider: str
    status: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    created_at: datetime

    class Config:
        from_attributes = True

class MetricsResponse(BaseModel):
    """Metrics response"""
    date: str
    provider: str
    model: str
    total_requests: int
    avg_latency_ms: int
    error_count: int
    total_cost_usd: float
    p95_latency_ms: Optional[int] = None
    p99_latency_ms: Optional[int] = None

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    database: str
    redis: str
    timestamp: datetime
