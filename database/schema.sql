-- PostgreSQL Schema for LLM Inference Logger

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Conversations table
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    title VARCHAR(255),
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'archived', 'cancelled')),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);

CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_status ON conversations(status);
CREATE INDEX idx_conversations_created_at ON conversations(created_at DESC);
CREATE INDEX idx_conversations_deleted_at ON conversations(deleted_at);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    tokens_estimated INT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_created_at ON messages(created_at DESC);
CREATE INDEX idx_messages_role ON messages(role);

-- Inference Logs table
CREATE TABLE IF NOT EXISTS inference_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    
    -- Request info
    model VARCHAR(255) NOT NULL,
    provider VARCHAR(100) NOT NULL,
    request_preview TEXT,
    
    -- Response info
    status VARCHAR(50) NOT NULL CHECK (status IN ('success', 'error', 'timeout')),
    response_preview TEXT,
    error_message TEXT,
    
    -- Metrics
    input_tokens INT DEFAULT 0,
    output_tokens INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    latency_ms INT,
    
    -- Cost tracking
    cost_usd DECIMAL(10, 6) DEFAULT 0,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_inference_logs_conversation_id ON inference_logs(conversation_id);
CREATE INDEX idx_inference_logs_model_provider ON inference_logs(model, provider);
CREATE INDEX idx_inference_logs_status ON inference_logs(status);
CREATE INDEX idx_inference_logs_created_at ON inference_logs(created_at DESC);
CREATE INDEX idx_inference_logs_metadata ON inference_logs USING GIN(metadata);

-- Metrics Aggregated table
CREATE TABLE IF NOT EXISTS metrics_aggregated (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    provider VARCHAR(100) NOT NULL,
    model VARCHAR(255) NOT NULL,
    
    -- Counters
    total_requests INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    error_count INT DEFAULT 0,
    timeout_count INT DEFAULT 0,
    
    -- Computed metrics
    avg_latency_ms INT,
    p50_latency_ms INT,
    p95_latency_ms INT,
    p99_latency_ms INT,
    min_latency_ms INT,
    max_latency_ms INT,
    
    total_cost_usd DECIMAL(12, 6) DEFAULT 0,
    avg_cost_per_request DECIMAL(10, 6),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(date, provider, model)
);

CREATE INDEX idx_metrics_aggregated_date_provider ON metrics_aggregated(date DESC, provider);
CREATE INDEX idx_metrics_aggregated_date_model ON metrics_aggregated(date DESC, model);

-- Failed Logs (Dead Letter Queue)
CREATE TABLE IF NOT EXISTS failed_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payload JSONB NOT NULL,
    error_message TEXT,
    retry_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_failed_logs_created_at ON failed_logs(created_at DESC);
CREATE INDEX idx_failed_logs_retry_count ON failed_logs(retry_count);

-- Audit Log table
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255),
    action VARCHAR(255) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    details JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER conversations_updated_at BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER messages_updated_at BEFORE UPDATE ON messages
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER inference_logs_updated_at BEFORE UPDATE ON inference_logs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER metrics_aggregated_updated_at BEFORE UPDATE ON metrics_aggregated
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER failed_logs_updated_at BEFORE UPDATE ON failed_logs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
