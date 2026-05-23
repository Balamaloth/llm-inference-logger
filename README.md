# LLM Inference Logger & Ingestion System

A lightweight, end-to-end logging and ingestion system for LLM applications. Capture inference metadata, stream responses, and analyze performance metrics in real-time.

## Features

✅ **Multi-turn Chatbot** - React-based UI with conversation management <br>
✅ **Lightweight SDK** - Non-intrusive instrumentation wrapper for LLM calls <br>
✅ **Real-time Ingestion** - Event-based log collection and processing <br>
✅ **Performance Analytics** - Latency, throughput, and error dashboards <br>
✅ **Multi-provider Support** - OpenAI, Anthropic, Google Gemini, DeepSeek <br>
✅ **Streaming Responses** - Real-time token streaming with proper logging <br>
✅ **PII Redaction** - Automatic sensitive data masking <br>
✅ **Docker Compose** - One-command local setup <br>
✅ **Kubernetes Ready** - Self-hosted K8s deployment configs <br>
✅ **Conversation Management** - Resume, cancel, and list conversations <br>

## Project Structure

```
llm-inference-logger/
├── backend/
│   ├── sdk/                    # Lightweight logging SDK
│   │   ├── __init__.py
│   │   ├── client.py          # Main SDK client
│   │   ├── middleware.py      # LLM middleware wrapper
│   │   ├── pii_redactor.py    # PII masking
│   │   └── config.py          # SDK configuration
│   ├── ingestion/             # Log ingestion service
│   │   ├── main.py            # FastAPI app
│   │   ├── models.py          # Data models
│   │   ├── db.py              # Database layer
│   │   ├── handlers.py        # Event handlers
│   │   └── validators.py      # Payload validation
│   ├── migrations/            # Database migrations
│   ├── requirements.txt       # Python dependencies
│   └── Dockerfile            # Backend container
├── frontend/
│   ├── src/
│   │   ├── components/        # React components
│   │   ├── pages/            # Pages
│   │   ├── services/         # API services
│   │   └── App.tsx
│   ├── package.json
│   └── Dockerfile            # Frontend container
├── database/
│   ├── schema.sql            # Database schema
│   └── init.sql              # Initial data
├── docker-compose.yml        # Full stack orchestration
├── kubernetes/               # K8s manifests
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   └── configmap.yaml
└── ARCHITECTURE.md           # Detailed architecture notes
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js 18+
- PostgreSQL 15+ (or use Docker)

### 1. Clone and Setup

```bash
git clone https://github.com/Balamaloth/llm-inference-logger.git
cd llm-inference-logger
```

### 2. Environment Configuration

```bash
# Copy example env files
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Update `.env` with your LLM provider API keys:
```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
DATABASE_URL=postgresql://user:password@localhost:5432/llm_logger
```

### 3. One-Command Setup

```bash
docker-compose up -d
```

This starts:
- **Backend API**: http://localhost:8000
- **Frontend UI**: http://localhost:3000
- **PostgreSQL Database**: localhost:5432
- **Redis Cache**: localhost:6379
- **Ingestion Service**: http://localhost:8001

### 4. Verify Installation

```bash
# Check services
docker-compose ps

# View logs
docker-compose logs -f backend

# Access dashboard
open http://localhost:3000
```

## Architecture Overview

### System Architecture

```
┌─────────────────┐
│  Chatbot UI     │
│  (React)        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  LLM SDK        │
│  (Wrapper)      │
└────────┬────────┘
         │ (metadata)
         ▼
┌─────────────────┐         ┌──────────────────┐
│  LLM Provider   │ ────┬─► │  Ingestion API   │
│  (OpenAI, etc)  │    │    │  (FastAPI)       │
└─────────────────┘    │    └────────┬─────────┘
                       │             │
                       │    (validate, transform)
                       │             │
                       │             ▼
                       │    ┌─────────────────┐
                       │    │  Event Queue    │
                       │    │  (Redis)        │
                       │    └────────┬────────┘
                       │             │
                       │             ▼
                       │    ┌──────────────────┐
                       └──► │   PostgreSQL     │
                            │   (Persist)      │
                            └──────────────────┘
```

## Database Schema

### Tables

#### `conversations`
```sql
CREATE TABLE conversations (
  id UUID PRIMARY KEY,
  user_id VARCHAR(255),
  title VARCHAR(255),
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  status VARCHAR(50) -- active, archived, cancelled
);
```

#### `messages`
```sql
CREATE TABLE messages (
  id UUID PRIMARY KEY,
  conversation_id UUID REFERENCES conversations(id),
  role VARCHAR(50), -- user, assistant
  content TEXT,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);
```

#### `inference_logs`
```sql
CREATE TABLE inference_logs (
  id UUID PRIMARY KEY,
  conversation_id UUID REFERENCES conversations(id),
  model VARCHAR(255),
  provider VARCHAR(100),
  status VARCHAR(50), -- success, error
  input_tokens INT,
  output_tokens INT,
  total_tokens INT,
  latency_ms INT,
  cost_usd DECIMAL(10, 6),
  error_message TEXT,
  request_preview TEXT,
  response_preview TEXT,
  metadata JSONB,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);
```

#### `metrics_aggregated`
```sql
CREATE TABLE metrics_aggregated (
  id UUID PRIMARY KEY,
  provider VARCHAR(100),
  model VARCHAR(255),
  date DATE,
  total_requests INT,
  total_tokens INT,
  avg_latency_ms INT,
  error_count INT,
  total_cost_usd DECIMAL(10, 6),
  created_at TIMESTAMP
);
```

## SDK Usage

### Installation

```python
pip install llm-inference-logger
```

### Basic Usage

```python
from llm_sdk import LLMClient
import openai

# Initialize SDK
client = LLMClient(
    api_key="your-api-key",
    provider="openai",
    ingestion_endpoint="http://localhost:8001/api/logs"
)

# Wrap your LLM call
response = client.chat(
    conversation_id="conv-123",
    model="gpt-4",
    messages=[
        {"role": "user", "content": "Hello!"}
    ],
    stream=True
)

# Response is still a normal OpenAI response
# SDK logs automatically in background
for chunk in response:
    print(chunk.choices[0].delta.content, end="")
```

## License

MIT License - see LICENSE file

## Submission

Submit to: work@ollive.ai
- GitHub repo
- Architecture notes
- Demo link (optional)
