# Manus — Autonomous AI Software Engineer

> Give it a task in plain English.
> It plans, researches, writes production code, catches its own bugs, fixes them, runs tests, scores the output, and improves itself — **without you touching anything.**

---

## What it actually does

```
You:    "Build a URL shortener with analytics"

[Manus]      Analysing task → creating execution plan (ReAct reasoning)
[Research]   Searching docs, libraries, best practices...
[Research]   ⚡ Running in parallel with above...
[Coder]      Writing FastAPI backend, DB schema, analytics endpoints...
[Executor]   Running code in Docker sandbox...
[Error]      AttributeError: 'NoneType' has no attribute 'short_code'
[Debugger]   Identifying root cause → fixing null check... (attempt 1/3)
[Executor]   Running fixed code... ✅ Exit code 0
[Tests]      Generating pytest suite → running 12 tests...
[Tests]      9/12 passed (75% pass rate)
[Evaluator]  Score: 8.0/10 — Correctness 8.5 · Quality 7.5 · Complete 8.0
[Memory]     Solution saved to ChromaDB for future recall

Output:  app.py  models.py  analytics.py  test_solution.py  requirements.txt
```

**Total time: ~4 minutes. Zero human intervention.**

**Output:** Working FastAPI app with database schema, API endpoints, test suite, and evaluation score — all generated autonomously.

---

## Architecture

```
User Request
      ↓
   Manus  (Planner + Orchestrator)
      ↓
┌─────────────────────────────────────────────┐
│  ResearchAgent  — web search + doc lookup   │
│  CodingAgent    — LLM code generation       │
│  DebugAgent     — self-healing retry loop   │  ← 3 automatic retries
│  TestAgent      — pytest generation + run  │
└─────────────────────────────────────────────┘
      ↓
   Manus  (LLM-as-judge evaluation)
      ↓
   Improvement loop  (if score < 6/10)
      ↓
   ChromaDB  (stores solution for future recall)
```

---

## Self-Healing Loop

The system automatically fixes its own errors:

```python
# DebugAgent — app/agents/debug.py
for attempt in range(MAX_DEBUG_RETRIES):   # default: 3
    result = run_code(current_code)

    if result.success:
        remember_bug_fix(error, fix)        # persist to ChromaDB memory
        return fixed_code

    error = result.stderr
    current_code = kimi.fix(error, current_code)  # Groq/LLM fixes it

return "Failed after retries"
```

Every bug fix is stored in ChromaDB so the system learns from past mistakes.

---

## Key Features

| Feature | Implementation |
|---------|---------------|
| Multi-agent orchestration | Manus plans + delegates to specialist agents |
| Self-healing debug loop | DebugAgent retries up to 3× with LLM fixes |
| Sandboxed code execution | Isolated Docker container, memory/CPU limited |
| Persistent memory | ChromaDB vector store — recalls past solutions |
| Test generation + execution | TestAgent writes and runs pytest automatically |
| LLM-as-judge evaluation | Scores correctness, quality, completeness 0–10 |
| Improvement loop | Re-generates code if evaluation score < 6/10 |
| Real-time streaming | SSE stream — watch the pipeline live in the UI |
| Observability | Prometheus metrics — latency, success rate, score distribution |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | Manus (custom, this repo) |
| LLM Reasoning | Groq API (llama-3.1-8b-instant) |
| Backend | FastAPI + Uvicorn (4 workers) |
| Code Execution | Docker sandbox (isolated container) |
| Memory | ChromaDB vector store |
| Metrics | Prometheus + prometheus-fastapi-instrumentator |
| Containerisation | Docker Compose (4 services) |

---

## Project Structure

```
├── app/
│   ├── agents/
│   │   ├── manus.py          # Orchestrator — the brain
│   │   ├── orchestrator.py   # Execution engine
│   │   ├── research.py       # Web research agent
│   │   ├── coding.py         # Code generation agent
│   │   ├── debug.py          # Self-healing debug agent
│   │   ├── test_agent.py     # Test generation + execution
│   │   └── chat_agent.py     # Conversational interface
│   ├── core/
│   │   ├── kimi_client.py    # LLM client (OpenAI-compatible)
│   │   ├── memory/           # ChromaDB vector store
│   │   └── tools/            # code_runner, web_search, file_manager
│   ├── api/routes/           # FastAPI routes
│   ├── evaluation/           # LLM judge + Prometheus metrics
│   ├── models/               # Pydantic schemas
│   └── static/               # UI (dark-themed, real-time SSE)
├── sandbox/                  # Isolated code execution container
├── docker-compose.yml        # 4-service stack
└── prometheus.yml
```

---

## Running Locally

**Prerequisites:** Docker Desktop

```bash
git clone <repo>
cd autonomous-agent

cp .env.example .env
# Add your Groq API key (free at console.groq.com)
# KIMI_API_KEY=gsk_...
# KIMI_BASE_URL=https://api.groq.com/openai/v1
# KIMI_MODEL=llama-3.1-8b-instant

docker compose up --build
```

| Service | URL |
|---------|-----|
| UI | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Architecture | http://localhost:8000/api/v1/manus/info |
| Metrics | http://localhost:9090 |

**Run a task via API:**
```bash
curl -X POST http://localhost:8000/api/v1/agent/sync \
  -H "Content-Type: application/json" \
  -d '{"description": "Build a FastAPI todo app with JWT authentication"}'
```

---

## Evaluation Metrics

Every task is scored by the LLM judge:

| Metric | Description |
|--------|-------------|
| Correctness | Does the code solve the task? |
| Quality | Clean, idiomatic, no obvious bugs? |
| Completeness | All requirements addressed? |
| Test pass rate | % of generated tests passing |
| Latency | End-to-end execution time |

Scores and latency are tracked in Prometheus and visible in the UI.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/agent/run` | Run task, stream events (SSE) |
| `POST` | `/api/v1/agent/sync` | Run task, blocking response |
| `GET`  | `/api/v1/tasks/{id}` | Get task result |
| `POST` | `/api/v1/chat/` | Chat with Manus about the session |
| `GET`  | `/api/v1/manus/info` | Architecture overview |
| `GET`  | `/metrics` | Prometheus metrics |
| `GET`  | `/health` | Health check |

---

## What This Demonstrates

- **Systems design** — multi-service Docker architecture, async Python, SSE streaming
- **AI engineering** — multi-agent orchestration, prompt design, LLM-as-judge evaluation
- **Production thinking** — sandboxed execution, retry logic, observability, graceful error handling
- **Self-improving systems** — memory persistence, automatic debug loops, improvement cycles
