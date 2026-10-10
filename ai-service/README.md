# AIRS AI Service

The core multi-agent AI orchestration service for the Autonomous Incident Response System (AIRS). Built with LangGraph, ChromaDB, and Elasticsearch for intelligent incident investigation and root cause analysis.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│           Flask REST API (Port 5000)                │
└──────────────┬──────────────────────────────────────┘
               │
     ┌─────────┴─────────┐
     │                   │
┌────▼────────┐  ┌──────▼──────────┐
│ Orchestrator│  │ RAG Retriever   │
│ (LangGraph) │  │ (Hybrid Search) │
└────┬────────┘  └──────┬──────────┘
     │                   │
     │          ┌────────┴────────┐
     │          │                 │
     │    ┌─────▼──┐      ┌──────▼──┐
     │    │ ChromaDB│      │ Elasticsearch│
     │    │ (Vector)│      │ (Lexical)    │
     │    └────────┘      └──────────────┘
     │
     ├─► Log Analysis Agent
     ├─► Anomaly Detection Agent
     ├─► Context Retrieval Agent
     ├─► Root Cause Analysis Agent
     ├─► Risk Assessment Agent
     └─► Report Generation Agent
```

## Key Features

- **Multi-Agent Orchestration**: LangGraph-based workflow for coordinating specialized agents
- **Hybrid RAG**: Vector (ChromaDB) + Lexical (Elasticsearch) search for knowledge retrieval
- **Incident Investigation Pipeline**: 6-phase investigation workflow
- **LLM Integration**: Google Gemini API for reasoning
- **REST API**: Flask-based endpoints for investigation triggering and status tracking
- **Async Investigation**: Non-blocking investigation processing

## API Endpoints

### Health Check
```
GET /health
```

### Start Investigation
```
POST /api/investigate
Content-Type: application/json

{
  "incident_id": "INC-2024-001",
  "logs": ["log entry 1", "log entry 2"],
  "alerts": ["alert 1", "alert 2"],
  "context": "optional context"
}

Response (202 Accepted):
{
  "investigation_id": "uuid",
  "status": "in_progress"
}
```

### Get Investigation Status
```
GET /api/investigate/<investigation_id>

Response:
{
  "investigation_id": "uuid",
  "status": "completed|in_progress|failed",
  "root_cause": "string",
  "risk_assessment": {...},
  "recommendations": [...],
  "anomalies": [...],
  "errors": [...]
}
```

### RAG Search
```
POST /api/rag/search
Content-Type: application/json

{
  "query": "how to respond to unauthorized process execution",
  "top_k": 5
}

Response:
{
  "results": [
    {
      "id": "doc_001",
      "content": "...",
      "score": 0.95,
      "source": "vector|lexical",
      "metadata": {...}
    }
  ],
  "query": "...",
  "count": 5
}
```

### Ingest Documents
```
POST /api/rag/ingest
Content-Type: application/json

{
  "documents": [
    {
      "id": "doc_001",
      "content": "runbook content",
      "source": "runbooks",
      "metadata": {"category": "incident_response"}
    }
  ]
}

Response:
{
  "ingested": 1,
  "failed": 0
}
```

## Investigation Phases

1. **Log Analysis**: Parse, normalize, and structure log entries
2. **Anomaly Detection**: Identify suspicious patterns and deviations
3. **Context Retrieval**: Fetch relevant runbooks and historical incidents
4. **Root Cause Analysis**: Determine root cause using LLM reasoning
5. **Risk Assessment**: Calculate severity, blast radius, and attack patterns
6. **Report Generation**: Generate actionable recommendations

## Setup

### Prerequisites
- Python 3.11+
- ChromaDB instance (or use embedded mode)
- Elasticsearch instance
- Google Gemini API key

### Installation

1. **Clone and navigate to ai-service**:
   ```bash
   cd ai-service
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your settings, especially GOOGLE_API_KEY
   ```

5. **Start the service**:
   ```bash
   python app.py
   ```

The service will start on `http://localhost:5000`

## Development

### Running Tests
```bash
pytest tests/
```

### Project Structure
```
ai-service/
├── app.py                 # Flask application entry point
├── config.py             # Configuration management
├── requirements.txt      # Python dependencies
├── .env.example         # Environment template
├── agents/              # Agent implementations
│   ├── __init__.py
│   └── orchestrator.py  # Multi-agent orchestrator
├── rag/                 # RAG components
│   ├── __init__.py
│   └── retriever.py     # Hybrid search retriever
├── tests/               # Test suite
└── README.md           # This file
```

### Adding New Agents

1. Create agent function in `orchestrator.py`:
   ```python
   def _my_agent(self, state: InvestigationState) -> InvestigationState:
       # Agent logic
       return state
   ```

2. Add node to graph in `_build_graph()`:
   ```python
   workflow.add_node("my_agent", self._my_agent)
   ```

3. Define edges to integrate into workflow:
   ```python
   workflow.add_edge("previous_agent", "my_agent")
   ```

## Integration with Backend

The AI Service integrates with the Java backend via REST calls:
- Post investigation results
- Query incident database
- Fetch system context

Configure `BACKEND_SERVICE_URL` in `.env`

## Troubleshooting

**ChromaDB Connection Issues**
- Ensure ChromaDB is running: `docker run -p 8000:8000 chromadb/chroma`
- Check `CHROMADB_HOST` and `CHROMADB_PORT` in `.env`

**Elasticsearch Connection Issues**
- Ensure Elasticsearch is running on port 9200
- Check ES health: `curl http://localhost:9200/_cluster/health`

**Missing API Key**
- Set `GOOGLE_API_KEY` environment variable
- Get key from Google AI Studio: https://aistudio.google.com/

## License

AIRS is licensed under [License Type]. See LICENSE file for details.
