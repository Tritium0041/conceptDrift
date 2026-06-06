# ConceptDrift

ConceptDrift is a lightweight developer inspiration generator. It creates project-idea research reports with a local FastAPI backend, SQLite persistence, and a Next.js workspace UI.

## Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy, SQLite, in-process async worker
- Frontend: Next.js App Router, TypeScript, Tailwind CSS
- Agent provider: `mock` by default, direct Codex agent research via `codex`, lightweight Responses API via `response`

## Run Backend

```bash
cd backend
uv sync --dev
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The default SQLite database is created at `backend/data/conceptdrift.sqlite3`.

To use the Codex-backed provider:

```bash
cd backend
export CONCEPTDRIFT_AGENT_PROVIDER=codex
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-5
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Use `CONCEPTDRIFT_AGENT_PROVIDER=response` when you only want to test the OpenAI-compatible Responses API path without Codex agent research.

You can also configure the provider from the UI at [http://localhost:3000/settings](http://localhost:3000/settings).
The UI writes backend runtime settings to `backend/.env`; OpenAI keys are write-only in the API response and shown only as a masked value.

Provider modes:

- `mock`: deterministic local report, no API key.
- `codex`: OpenAI Agents SDK workflow plus direct Codex research threads. Codex researches external signals itself through browser/web-search/network tools, then an orchestrator agent streams the structured report.
- `response`: lightweight single Responses API call.

Generation modes:

- `guided`: default mode. The report is generated around the submitted `direction`.
- `yolo`: autonomous exploration mode. The agent does not require a user direction; Codex first searches current public web signals, selects an interesting research direction, then runs the normal multi-source report pipeline.

Credentials:

- OpenAI uses `OPENAI_API_KEY`; there is no separate AK/SK pair.
- Codex research uses the experimental Codex SDK path from `openai-agents` through direct Codex threads.
- GitHub, Hacker News, Product Hunt, and Reddit sources are researched by Codex instead of backend source-scraping APIs.

## Run Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Validation

```bash
cd backend && uv run pytest
cd frontend && npm run lint && npm run build
```

## API

- `POST /api/tasks/generate`
- `POST /api/tasks/{task_id}/resume`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/events`
- `GET /api/tasks/{task_id}/result`
- `GET /api/config`
- `PUT /api/config`
- `GET /api/reports`
- `GET /api/reports/{report_id}`
- `GET /api/reports/{report_id}/export?format=markdown|pdf`
- `GET /api/health`

Example YOLO request:

```bash
curl -X POST http://127.0.0.1:8000/api/tasks/generate \
  -H 'Content-Type: application/json' \
  -d '{"mode":"yolo","direction":"","sources":["github_trending","hackernews","product_hunt"],"depth":"standard"}'
```

Resume a failed task without losing completed research checkpoints:

```bash
curl -X POST http://127.0.0.1:8000/api/tasks/<task_id>/resume
```
