# Revenue Ops Copilot

An **AI Automation Agency (AAA)** lead qualification and outreach automation system built with **FastAPI**, **Temporal**, **PostgreSQL**, and **OpenAI**. The system ingests leads via webhook, qualifies them using LLM-driven scoring, drafts personalized outreach emails, and delivers them through an outbox-pattern sender worker with CRM integration.

---

## Architecture

```mermaid
graph TD
    A["Webhook POST"] --> B["FastAPI Gateway"]
    B -->|"dedupe + insert"| C["Temporal Workflow Engine"]
    C -->|"qualify (LLM)"| D{"Review Gate"}
    D -->|"approve"| E["draft (LLM)"]
    D -->|"cancel"| Z["CANCELLED"]
    E --> F{"Approval Gate"}
    F --> G["Write Outbox"]
    G --> H[("PostgreSQL")]
    H -->|"poll PENDING"| I["Sender Worker"]
    I --> J["SendGrid (Email)"]
    I --> K["HubSpot (CRM)"]
    C -->|"schedule"| L["FollowupWorkflow ×N"]
```

---

## Key Design Patterns

1. **Temporal Idempotency** — Deterministic workflow ID `lead:{tenant_id}:{external_lead_id}` + `REJECT_DUPLICATE`. Dual-layer dedupe with DB unique constraint.
2. **Outbox Pattern** — Workflows write side-effect intents to `outbox` table; sender worker polls and dispatches. No direct external calls from workflows.
3. **LLM Contract** — Parse → Repair → Fallback chain for every LLM call:

```mermaid
graph LR
    A["LLM Response"] --> B{"Parse OK?"}
    B -->|"yes"| C["Use Result"]
    B -->|"no"| D["Repair (gpt-4o-mini)"]
    D --> E{"Valid?"}
    E -->|"yes"| C
    E -->|"no"| F["Fallback Defaults"]
```

4. **Run Ledger** — Every LLM call recorded in `runs` table: model, prompt version, tokens, cost, schema validity, repair/fallback status, policy decision.
5. **Eval + CI Gates** — 50-sample golden dataset, 3 metrics, GitHub Actions regression gate on prompt/eval changes.

---

## Getting Started

### Prerequisites

- **Docker** and **Docker Compose**
- **Python 3.11+**
- **OpenAI API key** (for real LLM eval; not needed for tests)

### 1. Clone and Setup

```bash
git clone https://github.com/PrestoOverture/revenue_ops_copilot.git
cd revenue_ops_copilot

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

### 2. Start Infrastructure

```bash
docker-compose up -d
```

This starts:

- **PostgreSQL 15** on port `5432`
- **Temporal Server** on port `7233` (gRPC)
- **Temporal UI** on port `8080` (web dashboard)

Wait for all services to be healthy:

```bash
docker-compose ps
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```bash
DATABASE_URL=postgresql://revops:revops@localhost:5432/revops
TEMPORAL_ADDRESS=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=lead-processing
OPENAI_API_KEY=sk-...
EMAIL_PROVIDER=sendgrid
SENDGRID_API_KEY=SG-...
EMAIL_FROM=noreply@company.com
CRM_PROVIDER=hubspot
HUBSPOT_API_KEY=pat-...
ENCRYPTION_KEY=<32-byte-base64-key>
```

### 4. Run Migrations

```bash
alembic upgrade head
```

This creates 7 tables: `events`, `lead_state`, `outbox`, `runs`, `prompts`, `email_templates`, `tenant_config`.

### 5. Start the Application

Open 3 terminal windows:

```bash
# Terminal 1: API server
uvicorn src.api.main:app --reload

# Terminal 2: Temporal worker
python -m src.workers.temporal_worker

# Terminal 3: Sender worker
python -m src.workers.sender
```

The API is now available at `http://localhost:8000`. Temporal UI is at `http://localhost:8080`.

### 6. Try It Out

```bash
curl -X POST http://localhost:8000/webhooks/lead \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    "external_lead_id": "lead-001",
    "dedupe_key": "lead-001-v1",
    "event_type": "lead.created",
    "email": "vp@enterprise.com",
    "name": "Dana Patel",
    "company": "Enterprise Corp",
    "source": "demo_request"
  }'
```

Response:

```json
{
  "workflow_id": "lead:550e8400-e29b-41d4-a716-446655440000:lead-001",
  "status": "accepted"
}
```

Duplicate submissions return `"status": "duplicate"` — no error, no side effects.

Other endpoints:

```bash
curl http://localhost:8000/leads/{lead_id}                # Check lead status
curl -X POST http://localhost:8000/leads/{lead_id}/signal \
  -H "Content-Type: application/json" \
  -d '{"action": "approve"}'                              # Approve (or "cancel")
curl http://localhost:8000/health                          # Health check
```

---

## LLM Qualification

The qualification prompt (`qualify_v2.0`) scores leads across 5 dimensions:


| Dimension           | Values                                   | Description                         |
| ------------------- | ---------------------------------------- | ----------------------------------- |
| **Priority**        | P0, P1, P2, P3                           | Enterprise → Individual             |
| **Budget Range**    | enterprise, mid_market, smb, unknown     | Inferred from signals               |
| **Timeline**        | immediate, 30_days, 90_days, exploratory | Intent-based inference              |
| **Routing**         | AUTO, REQUIRE_REVIEW                     | Determines if human approval needed |
| **Policy Decision** | ALLOW, BLOCK, REQUIRE_REVIEW             | Safety/compliance gate              |


### Priority Tiers

- **P0 (Enterprise, High Intent)**: C-suite/VP titles + business email + demo_request/pricing_page
- **P1 (Mid-Market, Moderate Intent)**: Director/Manager titles + business email + webinar/whitepaper
- **P2 (SMB or Exploratory)**: Real company but unclear size + blog_post/organic_search
- **P3 (Individual, Not Qualified)**: No real company + personal email (gmail, yahoo, etc.)

---

## Eval Pipeline

### Dataset

50 golden samples in `eval/dataset.jsonl` covering the full priority spectrum:


| Tier            | Count | Coverage                                       |
| --------------- | ----- | ---------------------------------------------- |
| P0 (Enterprise) | 8     | C-suite, VP, demo requests, pricing pages      |
| P1 (Mid-Market) | 12    | Directors, managers, webinars, whitepapers     |
| P2 (SMB)        | 15    | Small companies, blog visitors, organic search |
| P3 (Individual) | 10    | Freelancers, students, personal email          |
| Edge Cases      | 5     | Spam/bots, competitors, blocked domains        |


### Metrics

**Priority Accuracy** — Exact match between predicted and expected priority tier (P0/P1/P2/P3). Measures how well the LLM distinguishes enterprise leads from individuals.

**Schema Valid Rate** — Percentage of LLM responses that parse into valid JSON (no repair needed).

**Compliance Score** — Weighted score on whether the model correctly ALLOW/BLOCK/REQUIRE_REVIEW the lead

- +1 for correct decisions
- -0.2 for false positives (REQUIRE_REVIEW when should ALLOW)
- -0.5 for false negatives (ALLOW when should BLOCK/REQUIRE_REVIEW) 
- -1.0 for incorrect BLOCK decisions 
Normalized to [0, 1]

### Eval Results


| Metric            | Baseline | Prompt Version |
| ----------------- | -------- | -------------- |
| Priority Accuracy | 0.74     | `qualify_v2.0` |
| Schema Valid Rate | 1.00     | `qualify_v2.0` |
| Compliance Score  | 0.805    | `qualify_v2.0` |


### Running the Eval

```bash
# Real LLM eval (requires OPENAI_API_KEY)
python -m eval.run_eval

# Mock eval (deterministic, for CI smoke test)
python -m eval.run_eval --mock

# Compare against baseline
python -m eval.compare
```

### CI Regression Gate

Two CI jobs run on every push/PR to `main`:

- **Smoke** (every push): Runs mock eval to verify pipeline code isn't broken
- **Regression** (only when `src/llm/**` or `eval/**` change): Runs real LLM eval against 50 samples and enforces regression thresholds:


| Metric            | Max Allowed Regression |
| ----------------- | ---------------------- |
| Priority Accuracy | 3%                     |
| Schema Valid Rate | 2%                     |
| Compliance Score  | 10%                    |


---

## Testing

### Run Tests

```bash
# All tests
pytest

# Unit tests only (fast, no external deps)
pytest tests/ --ignore=tests/integration/

# Integration tests (requires Docker services running)
pytest tests/integration/

# With coverage
pytest --cov=src --cov-report=term-missing
```

### Test Coverage

- **~170+ unit tests** covering all modules
- **5 integration tests** with real PostgreSQL + real Temporal test server:
  - Happy path (full lifecycle)
  - Approval approve flow
  - Approval cancel flow
  - Idempotency / duplicate webhook
  - LLM failure fallback chain

### Lint and Type Check

```bash
ruff check src/ tests/ eval/
mypy src/
```

---

## Project Structure

```
revenue_ops_copilot/
├── src/
│   ├── api/            # FastAPI gateway
│   ├── workflows/      # Temporal workflows
│   ├── activities/     # Temporal activities
│   ├── workers/        # Worker processes
│   ├── llm/            # LLM client + prompts
│   ├── templates/      # Fallback email templates
│   └── db/             # asyncpg queries + pool
├── eval/
│   ├── dataset.jsonl   # 50 golden samples
│   ├── baseline.json   # Real LLM baseline
│   ├── run_eval.py     # Eval runner
│   ├── metrics.py      # 3 metric functions
│   └── compare.py      # Regression gate
├── tests/              # ~170 unit + 5 integration
├── migrations/         # 7 Alembic migrations
├── .github/workflows/  # CI eval gate
├── docker-compose.yml  # Postgres + Temporal
└── docs/               # Design docs
```

---

## Database Schema

7 tables managed by Alembic migrations:


| Table             | Purpose                                                   |
| ----------------- | --------------------------------------------------------- |
| `events`          | Immutable ingestion log with tenant-scoped dedupe         |
| `lead_state`      | Canonical lead state machine with qualification metadata  |
| `outbox`          | Side-effect queue with idempotency keys and retry backoff |
| `runs`            | LLM telemetry ledger (model, tokens, cost, policy traces) |
| `prompts`         | Prompt registry with tenant/system-default versioning     |
| `email_templates` | Tenant-owned email templates                              |
| `tenant_config`   | Per-tenant configuration with encrypted credentials       |


---

## Outbox Reliability

```mermaid
graph LR
    A["PENDING"] --> B["PROCESSING"]
    B --> C["SENT"]
    B -->|"error"| D["Retry + backoff (1m, 5m, 30m, 1h)"]
    D --> A
    D -->|"max attempts"| E["FAILED"]
    B -->|"stuck > 5min"| A
```

- **Error isolation**: One failure never blocks other records
- **Idempotency keys**: Prevent duplicate sends (`{lead_id}:email:{touchpoint}`)