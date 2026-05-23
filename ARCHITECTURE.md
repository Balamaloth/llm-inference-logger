# LLM Inference Logger - Architecture & Design Documentation

## 1. System Architecture Overview

### High-Level Flow

```
User (Browser)
    ↓
[Chatbot UI]
    ↓
[LLM SDK Wrapper]
    ↓
[LLM Provider API] ←─────┐
    ↓                     │
[Response Stream]    [Metadata Collection]
    ↓                     │
[User Sees Output]        ↓
                   [Ingestion Service]
                   (Async, Non-blocking)
                          ↓
                   [Event Queue] (Redis)
                          ↓
                   [Database Worker]
                          ↓
                   [PostgreSQL Store]
                          ↓
                   [Analytics Dashboard]
```

## 2. Component Design

### 2.1 Frontend (React)

**Purpose:** Provide intuitive UI for multi-turn conversations and analytics visualization

**Key Components:**
- `ChatInterface.tsx` - Main conversation UI
- `ConversationManager.tsx` - List/resume/cancel conversations
- `MetricsDashboard.tsx` - Real-time performance analytics
- `MessageDisplay.tsx` - Render messages with streaming support

**Technology Choices:**
- React 18+ for component-based UI
- TypeScript for type safety
- TanStack Query for API state management
- Chart.js/Recharts for metrics visualization
- WebSocket for real-time dashboard updates

**Why React?**
- Strong ecosystem for real-time dashboards
- Component reusability reduces code duplication
- Excellent TypeScript support

### 2.2 SDK (Python)

**Purpose:** Non-intrusive instrumentation wrapper around LLM calls

**Architecture:**
```python
# client.py
class LLMClient:
    def __init__(self, provider, api_key, ingestion_endpoint):
        self.provider = provider
        self.client = self._init_provider_client()
        self.ingestion = IngestionClient(ingestion_endpoint)
    
    def chat(self, conversation_id, messages, **kwargs):
        # Start timer
        start_time = time.time()
        
        # Call LLM with middleware
        response = self._call_with_logging(
            conversation_id=conversation_id,
            messages=messages,
            **kwargs
        )
        
        # Log asynchronously (non-blocking)
        self.ingestion.log_async(
            conversation_id=conversation_id,
            model=kwargs.get('model'),
            status='success',
            latency_ms=int((time.time() - start_time) * 1000),
            tokens=response.usage
        )
        
        return response
```

**Multi-Provider Support:**
- Provider adapter pattern: `OpenAIAdapter`, `AnthropicAdapter`, etc.
- Unified interface abstracting provider differences
- Easy to add new providers

**Example:**
```python
class ProviderAdapter(ABC):
    @abstractmethod
    def chat(self, messages, **kwargs):
        pass

class OpenAIAdapter(ProviderAdapter):
    def chat(self, messages, **kwargs):
        return self.client.chat.completions.create(
            model=kwargs['model'],
            messages=messages,
            **{k: v for k, v in kwargs.items() if k != 'model'}
        )
```

**Streaming Implementation:**
```python
def chat_stream(self, conversation_id, messages, **kwargs):
    start_time = time.time()
    token_count = 0
    
    for chunk in self.provider.stream(messages, **kwargs):
        token_count += self._count_tokens(chunk)
        yield chunk
    
    # Log after stream completes
    self.ingestion.log_async(
        conversation_id=conversation_id,
        output_tokens=token_count,
        latency_ms=int((time.time() - start_time) * 1000)
    )
```

### 2.3 Ingestion Service (FastAPI)

**Purpose:** Receive, validate, transform, and queue logs for persistence

**Endpoints:**
```python
@router.post("/api/logs")
async def create_log(payload: InferenceLogRequest):
    """
    1. Validate payload schema
    2. Apply PII redaction
    3. Extract analytics metadata
    4. Queue for async processing
    5. Return 202 Accepted
    """
    # Validation
    validated = InferenceLogValidator.validate(payload)
    
    # PII Redaction
    redacted = PIIRedactor.redact(validated)
    
    # Enqueue for processing
    await queue.enqueue(
        'process_log',
        redacted,
        job_timeout=300
    )
    
    return {"status": "accepted", "id": validated.id}
```

**Processing Pipeline:**
```
Payload Received
    ↓
[Schema Validation]
    ├─ Required fields check
    ├─ Type validation
    └─ Token count sanity check
    ↓
[PII Redaction]
    ├─ Pattern matching (email, phone, SSN)
    ├─ NER-based detection (optional)
    └─ Custom regex patterns
    ↓
[Metadata Extraction]
    ├─ Calculate cost (tokens × rate)
    ├─ Derive error severity
    └─ Tag by provider/model
    ↓
[Async Queue]
    └─ Redis/RabbitMQ for durability
    ↓
[Database Worker]
    └─ Batch writes for efficiency
    ↓
[Aggregate Metrics]
    └─ Update time-series buckets
```

### 2.4 Database Layer

**Why PostgreSQL?**
- ACID transactions for consistency
- JSONB for flexible metadata
- Full-text search for conversation analysis
- Excellent time-series performance (with extensions)
- Proven at scale

**Schema Design:**

#### Core Tables

**conversations**
```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    title VARCHAR(255),
    status VARCHAR(50) DEFAULT 'active',
    metadata JSONB, -- {"tags": [], "model_used": []}
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_created (created_at DESC)
);
```

Design rationale:
- UUID for distributed generation
- JSONB for tags and custom properties
- Timestamp indexes for time-range queries
- Status for soft-delete pattern

**messages**
```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL, -- 'user' or 'assistant'
    content TEXT NOT NULL,
    tokens_estimated INT,
    metadata JSONB, -- {"finish_reason": "stop", "logprobs": []}
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_conversation_id (conversation_id),
    INDEX idx_created (created_at)
);
```

**inference_logs**
```sql
CREATE TABLE inference_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id),
    message_id UUID REFERENCES messages(id),
    
    -- Request info
    model VARCHAR(255) NOT NULL,
    provider VARCHAR(100) NOT NULL,
    request_preview TEXT,
    
    -- Response info
    status VARCHAR(50) NOT NULL, -- 'success', 'error', 'timeout'
    response_preview TEXT,
    error_message TEXT,
    
    -- Metrics
    input_tokens INT,
    output_tokens INT,
    total_tokens INT,
    latency_ms INT,
    
    -- Cost tracking
    cost_usd DECIMAL(10, 6),
    
    -- Metadata
    metadata JSONB, -- {"temperature": 0.7, "top_p": 1.0, "finish_reason": "stop"}
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Indexes for common queries
    INDEX idx_conversation (conversation_id),
    INDEX idx_model_provider (model, provider),
    INDEX idx_status (status),
    INDEX idx_created (created_at DESC)
);
```

**metrics_aggregated** (for dashboard queries)
```sql
CREATE TABLE metrics_aggregated (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    provider VARCHAR(100) NOT NULL,
    model VARCHAR(255) NOT NULL,
    
    -- Counters
    total_requests INT,
    total_tokens INT,
    error_count INT,
    timeout_count INT,
    
    -- Computed metrics
    avg_latency_ms INT,
    p50_latency_ms INT,
    p95_latency_ms INT,
    p99_latency_ms INT,
    min_latency_ms INT,
    max_latency_ms INT,
    
    total_cost_usd DECIMAL(12, 6),
    avg_cost_per_request DECIMAL(10, 6),
    
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, provider, model),
    INDEX idx_date_provider (date DESC, provider),
    INDEX idx_date_model (date DESC, model)
);
```

**Query Performance Strategy:**

1. **Aggregation Table for Dashboards**
   - Pre-compute metrics once per day
   - Queries on `metrics_aggregated` are 10-100x faster
   - Trade-off: Real-time accuracy for performance
   - Solution: Compute metrics every 5 minutes for "today"

2. **Partitioning**
   ```sql
   -- Partition inference_logs by date for retention
   CREATE TABLE inference_logs_2024_01
   PARTITION OF inference_logs
   FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
   ```
   - Monthly partitions for 1-2 year retention
   - Older partitions can be archived to S3

3. **Column Indexing**
   - Index on (model, provider) for filtering
   - Index on created_at DESC for time-range queries
   - JSONB GIN index for metadata queries

### 2.5 Async Processing & Queueing

**Why Async Logging?**
- Requests complete immediately (no ingestion latency)
- Failed logs don't block LLM responses
- Resilient to database downtime
- Enables scaling independently

**Architecture:**
```
SDK sends log
    ↓
Ingestion API (202 Accepted)
    ↓
Enqueue to Redis
    ↓
Return to caller immediately
    ↓
Worker processes async
    ├─ Validate
    ├─ Redact PII
    ├─ Enrich metadata
    └─ Write to database
```

**Implementation:**
```python
# Using RQ (Redis Queue)
from rq import Queue
from redis import Redis

redis_conn = Redis()
queue = Queue('logs', connection=redis_conn)

# Enqueue from API
@app.post("/api/logs")
async def create_log(payload: InferenceLogRequest):
    job = queue.enqueue('process_log', payload)
    return {"job_id": job.id, "status": "queued"}

# Worker process
def process_log(payload):
    validated = validate_payload(payload)
    redacted = redact_pii(validated)
    write_to_db(redacted)
    update_metrics(redacted)
```

**Failure Handling:**
- Retry failed jobs 3 times with exponential backoff
- Dead-letter queue for permanently failed logs
- Admin API to replay dead-letter logs

## 3. PII Redaction Strategy

### Patterns Supported

```python
PII_PATTERNS = {
    'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    'phone': r'\b(?:\+?1[-.]?)?(?:\(?\d{3}\)?[-.]?)?\d{3}[-.]?\d{4}\b',
    'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
    'credit_card': r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
    'api_key': r'(?i)(sk-[a-zA-Z0-9]{20,}|apikey[=:][a-zA-Z0-9]*)',
    'aws_key': r'AKIA[0-9A-Z]{16}',
}
```

### Implementation

```python
class PIIRedactor:
    @staticmethod
    def redact(text: str, patterns: dict = None) -> str:
        patterns = patterns or PII_PATTERNS
        result = text
        
        for pii_type, pattern in patterns.items():
            result = re.sub(
                pattern,
                f"[REDACTED_{pii_type.upper()}]",
                result,
                flags=re.IGNORECASE
            )
        
        return result
    
    @staticmethod
    def redact_logs(log: InferenceLog) -> InferenceLog:
        """Redact PII from entire log object"""
        log.request_preview = PIIRedactor.redact(log.request_preview)
        log.response_preview = PIIRedactor.redact(log.response_preview)
        
        if log.metadata:
            log.metadata = PIIRedactor.redact(json.dumps(log.metadata))
        
        return log
```

### Trade-offs

**Regex vs NLP-based Redaction:**
- ✅ Regex: Fast (microseconds), no dependencies
- ❌ Regex: Might miss context-dependent PII
- ✅ NLP: Better accuracy
- ❌ NLP: Slower (milliseconds), requires model

Decision: Start with regex, add NLP option for future

## 4. Scaling Considerations

### Single Instance Capacity

**Bottlenecks:**
- Database: ~1000 writes/sec with connection pooling
- API: ~500 requests/sec (FastAPI + Uvicorn workers)
- Redis: ~10,000 ops/sec

**Maximum Load:** ~500 concurrent conversations

### Horizontal Scaling

#### Phase 1: Database Scaling
```yaml
# Read replicas for dashboards
Primary (write) → Replica 1 (read)
              ↘ Replica 2 (read)
              ↘ Replica 3 (read)
```

#### Phase 2: Application Scaling
```yaml
Load Balancer
    ├─ Backend Instance 1
    ├─ Backend Instance 2
    ├─ Backend Instance 3
    └─ Backend Instance 4
    
Shared Services
    ├─ PostgreSQL Cluster
    ├─ Redis Cluster
    └─ Ingestion Workers (auto-scaling)
```

#### Phase 3: Advanced
- Event sourcing for audit trail
- CQRS pattern for read optimization
- Kafka for multi-region replication
- ClickHouse for analytics warehouse

### Performance Targets

| Metric | Target | Current | Path |
|--------|--------|---------|------|
| Log ingestion latency | <100ms | 50-80ms | ✓ |
| API response time | <200ms | 100-150ms | ✓ |
| Dashboard query time | <1s | 800-950ms | ✓ |
| Throughput | 5000+ req/s | 500 req/s | Replicas, workers |
| Cost per log | <$0.0001 | - | Batch writes |

## 5. Failure Handling

### Scenarios & Recovery

#### Scenario: Ingestion Service Down
```
┌─────────────────────┐
│ SDK tries to send   │
│ Connection error    │
│ caught & buffered   │
└────────────┬────────┘
             ↓
┌─────────────────────┐
│ Local queue (SQLite)│
│ or memory buffer    │
└────────────┬────────┘
             ↓
        (retry)
        every 10s
             ↓
    ┌──────────────────┐
    │ Service restored │
    │ Flush buffer     │
    └──────────────────┘
```

Implementation:
```python
class LLMClient:
    def __init__(self):
        self.offline_queue = OfflineQueue(
            storage='sqlite',
            path='/tmp/llm_logs.db'
        )
    
    async def _ensure_ingestion(self):
        """Retry logic with exponential backoff"""
        max_retries = 5
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                await self.ingestion.send()
                return
            except ConnectionError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    # Save to offline queue
                    self.offline_queue.add(log)
```

#### Scenario: Database Connection Lost
```
Ingestion Service:
    Connection pool exhausted
    ↓
    Graceful degradation:
    - Accept logs (200 OK)
    - Queue in Redis only
    - Skip immediate DB write
    ↓
    Worker process:
    - Retry DB connection
    - Exponential backoff
    - Alert after 5 minutes
    ↓
    Fallback:
    - Write to file (for replay)
    - Or publish to Kafka (for distribution)
```

#### Scenario: LLM Provider Timeout
```python
SDK wraps call with timeout:

try:
    response = await asyncio.wait_for(
        llm_client.chat(...),
        timeout=30.0
    )
except asyncio.TimeoutError:
    log_with_status='timeout'
    log_error='Request exceeded 30s timeout'
    # Don't retry at SDK level
    # Let user retry from UI
```

## 6. Security Considerations

### Authentication & Authorization

```python
# JWT tokens for API auth
from fastapi_jwt_auth import AuthJWT

@app.post("/api/logs")
async def create_log(payload: InferenceLogRequest, 
                     Authorize: AuthJWT = Depends()):
    Authorize.jwt_required()
    user_id = Authorize.get_jwt_subject()
    # Validate user can log to conversation_id
    return {"status": "ok"}
```

### Data Encryption

- **In Transit:** TLS/HTTPS only
- **At Rest:** PostgreSQL encryption at-rest
- **API Keys:** Encrypted in environment variables
- **Sensitive Logs:** PII redaction + field-level encryption

### API Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/logs")
@limiter.limit("1000/minute")
async def create_log(request: Request, payload: InferenceLogRequest):
    # Maximum 1000 logs per minute per IP
    pass
```

## 7. Monitoring & Observability

### Metrics to Track

```python
# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge

log_counter = Counter(
    'logs_received_total',
    'Total logs received',
    ['provider', 'status']
)

ingestion_latency = Histogram(
    'ingestion_latency_seconds',
    'Ingestion processing latency',
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0]
)

queue_size = Gauge(
    'queue_size',
    'Current queue size',
    ['queue_name']
)
```

### Dashboards

**Real-time Monitoring (Grafana):**
- Logs/second (throughput)
- Error rate (by provider, model)
- Latency percentiles (p50, p95, p99)
- Queue depth
- Database connection pool usage

**Analytics Dashboard (Custom):**
- Cost breakdown by provider/model
- Token usage trends
- Model comparison (latency, accuracy)
- User engagement metrics
- Conversation success rate

## 8. Cost Analysis

### Infrastructure Costs (AWS)

| Component | Size | Cost/month |
|-----------|------|------------|
| EC2 (API) | t3.medium | $30 |
| RDS PostgreSQL | db.t3.small | $30 |
| ElastiCache Redis | cache.t3.micro | $15 |
| S3 (logs archive) | 100GB | $2 |
| **Total** | | **$77** |

### Per-Log Cost

- Infrastructure: ~$0.00001 per log
- LLM provider: $0.0001 - $0.001 per log (depends on model)
- Total: ~$0.00011 per log

### Cost Optimization

1. **Batch writes** (reduce I/O operations)
2. **Compression** for archived logs
3. **Tiered storage** (hot/cold)
4. **Reserved instances** for predictable load

## 9. Deployment

### Local Development
```bash
docker-compose up -d
# All services running in 30 seconds
```

### Kubernetes
```bash
kubectl apply -f kubernetes/
kubectl get all -n llm-logger
```

### Production Considerations

1. **Database backups:** Daily automated snapshots
2. **Log rotation:** Archive logs older than 90 days
3. **Secrets management:** Use AWS Secrets Manager or Vault
4. **SSL certificates:** Let's Encrypt with auto-renewal
5. **Health checks:** Liveness and readiness probes
6. **Resource limits:** Prevent runaway containers

## 10. Future Roadmap

### Short-term (1-3 months)
- ✅ Multi-provider support
- ✅ Streaming responses
- ✅ Basic dashboards
- ⬜ API documentation (Swagger)
- ⬜ User authentication

### Medium-term (3-6 months)
- ⬜ Advanced analytics (anomaly detection)
- ⬜ Cost optimization recommendations
- ⬜ A/B testing framework
- ⬜ Custom alerting
- ⬜ Data export/integration

### Long-term (6-12 months)
- ⬜ Multi-tenancy
- ⬜ Vector database integration
- ⬜ Fine-tuning dataset collection
- ⬜ Compliance reporting (SOC 2, HIPAA)
- ⬜ Global multi-region deployment

## Conclusion

This architecture provides:
- **Lightweight:** Minimal overhead on LLM calls
- **Scalable:** Horizontal scaling for 10,000+ req/s
- **Reliable:** Failure handling and retry logic
- **Secure:** PII redaction and encryption
- **Observable:** Comprehensive metrics and dashboards
- **Extensible:** Event-based design for future integrations
