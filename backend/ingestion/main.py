from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime, timedelta
import logging
import uuid
from typing import List, Optional

from .db import Base, engine, get_db, Conversation, Message, InferenceLog, MetricsAggregated, FailedLog
from .models import (
    InferenceLogRequest, ConversationCreate, ConversationUpdate,
    MessageRequest, ConversationResponse, MessageResponse,
    InferenceLogResponse, MetricsResponse, HealthResponse
)
from .validators import PayloadValidator

# Create tables
Base.metadata.create_all(bind=engine)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LLM Inference Logger - Ingestion Service",
    description="Real-time log ingestion and processing for LLM applications",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Health Check
# ============================================================================

@app.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint"""
    try:
        db.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    return HealthResponse(
        status="healthy" if db_status == "healthy" else "degraded",
        database=db_status,
        redis="healthy",
        timestamp=datetime.utcnow()
    )

# ============================================================================
# Ingestion Endpoints
# ============================================================================

@app.post("/api/logs", status_code=202)
async def create_log(
    payload: InferenceLogRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Ingest inference log
    Returns 202 Accepted for async processing
    """
    payload_dict = payload.dict()
    
    # Validate
    is_valid, error_msg = PayloadValidator.validate(payload_dict)
    if not is_valid:
        logger.warning(f"Invalid payload: {error_msg}")
        return {"status": "rejected", "error": error_msg}
    
    # Sanitize
    sanitized = PayloadValidator.sanitize(payload_dict)
    
    # Process in background
    background_tasks.add_task(process_log, sanitized, db)
    
    return {"status": "accepted", "id": sanitized.get("request_id")}

# ============================================================================
# Conversation Management
# ============================================================================

@app.post("/api/conversations", response_model=ConversationResponse)
def create_conversation(
    data: ConversationCreate,
    db: Session = Depends(get_db)
):
    """Create a new conversation"""
    conversation = Conversation(
        user_id=data.user_id,
        title=data.title,
        metadata=data.metadata or {}
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    
    return conversation

@app.get("/api/conversations", response_model=List[ConversationResponse])
def list_conversations(
    user_id: str = Query(...),
    status: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """List conversations for a user"""
    query = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.deleted_at == None
    )
    
    if status:
        query = query.filter(Conversation.status == status)
    
    conversations = query.order_by(desc(Conversation.created_at)).offset(offset).limit(limit).all()
    
    return conversations

@app.get("/api/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db)
):
    """Get conversation details"""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.deleted_at == None
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return conversation

@app.get("/api/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
def get_conversation_messages(
    conversation_id: str,
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get messages for a conversation"""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.deleted_at == None
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at).offset(offset).limit(limit).all()
    
    return messages

@app.post("/api/conversations/{conversation_id}/messages", response_model=MessageResponse)
def add_message(
    conversation_id: str,
    data: MessageRequest,
    db: Session = Depends(get_db)
):
    """Add a message to conversation"""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    message = Message(
        conversation_id=conversation_id,
        role=data.role,
        content=data.content,
        tokens_estimated=data.tokens_estimated,
        metadata=data.metadata or {}
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    
    return message

@app.patch("/api/conversations/{conversation_id}")
def update_conversation(
    conversation_id: str,
    data: ConversationUpdate,
    db: Session = Depends(get_db)
):
    """Update conversation"""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    if data.title is not None:
        conversation.title = data.title
    if data.status is not None:
        conversation.status = data.status
    if data.metadata is not None:
        conversation.metadata = data.metadata
    
    db.commit()
    db.refresh(conversation)
    
    return {"status": "updated", "conversation": conversation}

@app.post("/api/conversations/{conversation_id}/cancel")
def cancel_conversation(
    conversation_id: str,
    db: Session = Depends(get_db)
):
    """Cancel a conversation"""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    conversation.status = "cancelled"
    db.commit()
    
    return {"status": "cancelled", "id": conversation_id}

# ============================================================================
# Metrics Endpoints
# ============================================================================

@app.get("/api/metrics", response_model=List[MetricsResponse])
def get_metrics(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db)
):
    """Get aggregated metrics"""
    start_date = datetime.utcnow().date() - timedelta(days=days)
    
    query = db.query(MetricsAggregated).filter(
        MetricsAggregated.date >= start_date
    )
    
    if provider:
        query = query.filter(MetricsAggregated.provider == provider)
    if model:
        query = query.filter(MetricsAggregated.model == model)
    
    metrics = query.order_by(desc(MetricsAggregated.date)).all()
    
    return metrics

@app.get("/api/metrics/summary")
def get_metrics_summary(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db)
):
    \"\"\"Get summary metrics across all providers/models\"\"\"
    start_date = datetime.utcnow().date() - timedelta(days=days)
    
    result = db.query(
        func.sum(MetricsAggregated.total_requests).label("total_requests"),
        func.sum(MetricsAggregated.total_tokens).label("total_tokens"),
        func.sum(MetricsAggregated.error_count).label("error_count"),
        func.avg(MetricsAggregated.avg_latency_ms).label("avg_latency_ms"),
        func.sum(MetricsAggregated.total_cost_usd).label("total_cost_usd"),
    ).filter(
        MetricsAggregated.date >= start_date
    ).first()
    
    return {
        "period_days": days,
        "total_requests": result[0] or 0,
        "total_tokens": result[1] or 0,
        "error_count": result[2] or 0,
        "avg_latency_ms": result[3] or 0,
        "total_cost_usd": result[4] or 0,
    }

# ============================================================================
# Helper Functions
# ============================================================================

def process_log(payload: dict, db: Session):
    """Process log entry and save to database"""
    try:
        conversation_id = payload.get("conversation_id")
        
        # Ensure conversation exists
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        
        if not conversation:
            conversation = Conversation(
                id=conversation_id,
                user_id=payload.get("user_id", "unknown"),
                title=f"Conversation {conversation_id[:8]}",
            )
            db.add(conversation)
            db.flush()
        
        # Create inference log
        inference_log = InferenceLog(
            conversation_id=conversation_id,
            model=payload.get("model"),
            provider=payload.get("provider"),
            status=payload.get("status"),
            latency_ms=payload.get("latency_ms"),
            input_tokens=payload.get("input_tokens", 0),
            output_tokens=payload.get("output_tokens", 0),
            total_tokens=payload.get("total_tokens", 0),
            cost_usd=payload.get("cost_usd", 0),
            request_preview=payload.get("request_preview"),
            response_preview=payload.get("response_preview"),
            error_message=payload.get("error_message"),
            metadata=payload.get("metadata", {}),
        )
        db.add(inference_log)
        db.commit()
        
        logger.info(f"Processed log for conversation {conversation_id}")
    
    except Exception as e:
        logger.error(f"Failed to process log: {str(e)}")
        # Save to failed logs table
        try:
            failed_log = FailedLog(
                payload=payload,
                error_message=str(e),
            )
            db.add(failed_log)
            db.commit()
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
