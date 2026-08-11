# M365 Copilot Prompt Analyser (containerised)

A self-hosted, containerised replacement for the Power Platform + Power BI **M365
Copilot Prompt Analyser**. It ingests Microsoft 365 Copilot prompts from Microsoft
Graph (app-only / client credentials), sends each **conversation** to an Azure
OpenAI model for quality / GCSE / sentiment / category scoring and sensitive-info
detection, stores the results in PostgreSQL, and serves a web dashboard. Runs
anywhere via Docker and deploys to Azure Container Apps.

## Deploy to Azure (one click)

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Floryanstrant%2FM365Copilot-Prompt-Analyser%2Fmain%2Finfra%2Fazuredeploy.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2Floryanstrant%2FM365Copilot-Prompt-Analyser%2Fmain%2Finfra%2FcreateUiDefinition.json)

The button provisions everything into a resource group of your choice: a PostgreSQL
flexible server, a Container Apps environment, and the **api** + **worker** container
apps (pulled as prebuilt public images from GitHub Container Registry). You only enter
an **admin password** — the database password and encryption keys are generated for
you. When the deployment finishes, open the `dashboardUrl` output, sign in, and
complete the in-app **Settings** to connect Microsoft Graph and Azure OpenAI.

> **Maintainers:** the button relies on public images. After the first run of the
> **Publish container images** workflow, set both GHCR packages
> (`m365copilot-prompt-analyser/api` and `.../worker`) to **Public** once, so Container
> Apps can pull them anonymously. See [`docs/deploy.md`](docs/deploy.md).

This is a sibling of
[`M365Copilot-Usage-Reporter`](https://github.com/loryanstrant/M365Copilot-Usage-Reporter)
and [`AgentQualityReporter`](https://github.com/loryanstrant/AgentQualityReporter)
and shares their scaffold (Python/FastAPI engine, Postgres, React dashboard,
one-click Azure deploy). The one addition here is an **LLM analysis stage**.

## What it replaces

The original solution was a Power Platform managed solution (4 Dataverse tables +
6 Power Automate flows) plus a Power BI report:

| Original (Power Platform) | Here |
| --- | --- |
| `DAILYCoordinator` + 3 child flows + manual importer | `worker` (async ingest + analysis; APScheduler cron / Container Apps Job) |
| Graph `getAllEnterpriseInteractions` (client secret) | `worker/graph.py` (MSAL client credentials, paged, throttle-aware) — **reuse the same app registration** |
| AI Builder "prompt & conversation analyser" prompt | `shared/analysis_prompts.py` → Azure OpenAI (Structured Outputs) |
| AI Builder "sensitivity evaluator" prompt (per prompt) | merged into the same call by default (see below) |
| Dataverse JSON-blob tables | relational Postgres (`prompts`, `prompt_analysis`, `conversation_analysis`) |
| Power BI report (5 pages) | React dashboard (rebuilt from the HTML mock-ups) |

## The analysis engine

* **Model-agnostic.** The Azure OpenAI **deployment name** is configuration, not
  code. Default is **`gpt-5.4-mini`** (a current GA Azure OpenAI model); switch to
  `gpt-5.6-terra` for higher accuracy or `gpt-5.4-nano` for lowest cost in
  **Settings**, no redeploy. Endpoint / api-version / key are entered in Settings
  and the key is stored Fernet-encrypted (never in the image).
* **One call per conversation (default).** The original ran the analyser once per
  conversation **and** the sensitivity prompt once *per prompt*. Here both are
  merged into a **single call per conversation** (`analysis_mode="combined"`) —
  turning `1 + N` model calls into `1`. Set `analysis_mode="split"` to run them
  separately (e.g. to route sensitivity to a cheaper model or an external PII
  service).
* **Structured Outputs.** Responses are constrained by a JSON schema, so parsing
  never relies on the model avoiding markdown; it falls back to `json_object` if a
  model/api-version does not support `json_schema`.
* **Incremental & idempotent.** Only prompts with `analysed = False` are picked
  up; each conversation is analysed as a unit so its aggregate scores stay
  consistent. Concurrency is bounded (`ANALYSIS_CONCURRENCY`) to respect AOAI
  quotas.

Prompt wording lives in `shared/analysis_prompts.py` (ported verbatim in intent
from the two original AI Builder prompts) — edit it freely; the JSON *shape* is
enforced separately in `shared/llm.py`.

## Stack

- **Engine / API:** Python 3.12, FastAPI, SQLAlchemy 2.x (async), Alembic, httpx,
  MSAL, APScheduler, Pydantic v2, psycopg v3, **openai** (Azure OpenAI).
- **Database:** PostgreSQL 16 (schema via Alembic).
- **Frontend:** React + Vite + TypeScript + Tailwind + Recharts.
- **Packaging:** Docker + docker-compose. Deploy: `azd` + Bicep → Azure Container Apps.

## Repo layout

```
/api         FastAPI: routes, auth, metrics, serves built frontend
/worker      engine: Graph client, transforms, LLM analysis, scheduler, backfill
/shared      SQLAlchemy models, db, config, crypto, llm, analysis prompts
/frontend    React + Vite app (5 dashboard pages)
/infra       Bicep + azure.yaml (azd) + one-click Deploy to Azure
/alembic     migrations
/tests       pytest
docker-compose.yml
.env.example
```

## Quick start (local)

```powershell
# 1. Env file + a Fernet key
Copy-Item .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# paste the printed value into FERNET_KEY in .env

# 2. Start the full stack (api + worker + postgres + frontend)
docker compose up --build
```

- **Dashboard:** http://localhost:5173
- **API + Swagger:** http://localhost:8000/docs
- **Health:** http://localhost:8000/health

> **Running alongside the sibling solutions?** Set `WEB_PORT`, `API_PORT` and
> `DB_PORT` in `.env` to avoid host-port clashes (defaults `5173` / `8000` /
> `5432`). Only the host side changes — container-internal wiring is unaffected,
> so nothing else needs updating. Adjust the URLs above to match your `WEB_PORT`
> / `API_PORT`.

Sign in with `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env`, open **Settings**,
enter:
1. **Microsoft Graph** — tenant / client / secret (app-only, permissions
   `AiEnterpriseInteraction.Read.All` + `Directory.Read.All`), **Test connection**.
2. **Azure OpenAI** — endpoint, deployment (e.g. `gpt-5.4-mini`), api-version, key,
   **Test AOAI**.

Then **Run ingest** (pulls + analyses recent prompts) or **Run backfill** for
history. Ingest automatically triggers analysis unless `ANALYSE_AFTER_INGEST=false`.

## Terminology

Microsoft Graph uses "session" and "interaction"; this project renames them
everywhere to **Conversation** (`conversation_id`) and **Prompt** (`prompt_id`).

## Data model

- **prompts** — one row per human prompt, incl. `prompt_text` and the sensitivity
  confidences (`name_confidence`, `sensitive_confidence`, `curse_confidence`) and
  an `analysed` flag.
- **prompt_analysis** — per-prompt quality / GCSE (goal/context/source/expectation)
  / sentiment / category + rationale.
- **conversation_analysis** — per-conversation sentiment, avg & overall quality,
  user-generated ratio, theme, insight, category, improvement, suggested starter
  prompt.
- plus `entra_users`, `licensed_users`, `license_counts`, `app_config`,
  `ingest_state`, `job_runs`, `app_users` (inherited from the sibling scaffold).

## Tests

```powershell
pip install -e ".[dev]"
pytest
```
