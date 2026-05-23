from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text, ForeignKey, Index, JSON, Boolean, Date
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import uuid
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://llm_user:llm_password@localhost:5432/llm_logger")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    status = Column(String(50), default="active", index=True)
    metadata = Column(JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    inference_logs = relationship("InferenceLog", back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    tokens_estimated = Column(Integer, nullable=True)
    metadata = Column(JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    conversation = relationship("Conversation", back_populates="messages")

class InferenceLog(Base):
    __tablename__ = "inference_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    
    model = Column(String(255), nullable=False)
    provider = Column(String(100), nullable=False)
    request_preview = Column(Text, nullable=True)
    
    status = Column(String(50), nullable=False, index=True)
    response_preview = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, nullable=True)
    
    cost_usd = Column(Float, default=0.0)
    metadata = Column(JSONB, default={})
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    conversation = relationship("Conversation", back_populates="inference_logs")
    
    __table_args__ = (
        Index("idx_inference_logs_model_provider", "model", "provider"),
    )

class MetricsAggregated(Base):
    __tablename__ = "metrics_aggregated"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date = Column(Date, nullable=False)
    provider = Column(String(100), nullable=False)
    model = Column(String(255), nullable=False)
    
    total_requests = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    timeout_count = Column(Integer, default=0)
    
    avg_latency_ms = Column(Integer, nullable=True)
    p50_latency_ms = Column(Integer, nullable=True)
    p95_latency_ms = Column(Integer, nullable=True)
    p99_latency_ms = Column(Integer, nullable=True)
    min_latency_ms = Column(Integer, nullable=True)
    max_latency_ms = Column(Integer, nullable=True)
    
    total_cost_usd = Column(Float, default=0.0)
    avg_cost_per_request = Column(Float, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_metrics_date_provider", "date", "provider"),
        Index("idx_metrics_date_model", "date", "model"),
    )

class FailedLog(Base):
    __tablename__ = "failed_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payload = Column(JSONB, nullable=False)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
