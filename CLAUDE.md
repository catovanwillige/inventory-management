# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Factory Inventory Management System Demo with GitHub integration - Full-stack application with Vue 3 frontend, Python FastAPI backend, and in-memory mock data (no database).

> ⚠️ **This repository and any fork you create are PUBLIC.** Do not commit credentials, internal hostnames, or private registry URLs. `client/.npmrc` pins the public npm registry and `client/package-lock.json` is gitignored to prevent locally-configured registries from leaking into commits — leave both in place.

## Critical Tool Usage Rules

### Subagents
Use the Task tool with these specialized subagents for appropriate tasks:

- **vue-expert**: Use for Vue 3 frontend features, UI components, styling, and client-side functionality
  - Examples: Creating components, fixing reactivity issues, performance optimization, complex state management
  - **MANDATORY RULE: ANY time you need to create or significantly modify a .vue file, you MUST delegate to vue-expert**
- **code-reviewer**: Use after writing significant code to review quality and best practices
- **Explore**: Use for understanding codebase structure, searching for patterns, or answering questions about how components work
- **general-purpose**: Use for complex multi-step tasks or when other agents don't fit

### Skills
- **backend-api-test** skill: Use when writing or modifying tests in `tests/backend` directory with pytest and FastAPI TestClient

### MCP Tools
- **ALWAYS use GitHub MCP tools** (`mcp__github__*`) for ALL GitHub operations
  - Exception: Local branches only - use `git checkout -b` instead of `mcp__github__create_branch`
- **ALWAYS use Playwright MCP tools** (`mcp__playwright__*`) for browser testing
  - Test against: `http://localhost:3000` (frontend), `http://localhost:8001` (API)

## Stack
- **Frontend**: Vue 3 + Composition API + Vite (port 3000)
- **Backend**: Python FastAPI (port 8001)
- **Data**: JSON files in `server/data/` loaded via `server/mock_data.py`

## Commands

```bash
# Start / stop both servers (macOS/Linux; installs deps if missing)
./scripts/start.sh
./scripts/stop.sh

# Backend only (http://localhost:8001, docs at /docs)
cd server && uv sync && uv run python main.py

# Frontend only (http://localhost:3000)
cd client && npm install && npm run dev
cd client && npm run build      # production build -> client/dist/

# Backend tests. pytest is a dev dependency of the server/ project, so you
# must use --project ../server. Plain `cd tests && uv run pytest` (as tests/README.md says) fails.
cd tests && uv run --project ../server pytest
cd tests && uv run --project ../server pytest backend/test_inventory.py
cd tests && uv run --project ../server pytest backend/test_inventory.py::TestInventoryEndpoints::test_get_all_inventory
```

No linter, type checker, or frontend test suite is set up. `tests/README.md` is out of date: it lists a `test_orders.py` file that doesn't exist, and its test counts are wrong.

## Architecture

**Data flow**: shared filter state (`client/src/composables/useFilters.js`) → `client/src/api.js` (axios, hardcoded `http://localhost:8001/api`) → FastAPI in `server/main.py` → list comprehensions over in-memory data → Pydantic `response_model` → computed properties in views.

**Mock data**: `server/mock_data.py` loads every `server/data/*.json` file once, at import. No data is persisted, so a restart resets it. `server/generate_data.py` generates the JSON files.

**Filters**:
- `useFilters` keeps its refs at module level, so every view shares one filter state.
- The UI's "location" filter is sent to the API as `warehouse`, and "period" as `month`.
- The value `'all'` means "no filter". `api.js` leaves it out of the query string, and the backend helpers ignore it.
- In `server/main.py`, `apply_filters()` matches warehouse exactly, and category/status case-insensitively.
- `filter_by_month()` accepts `YYYY-MM` or a quarter (`Q1-2025`…`Q4-2025`, from the hardcoded `QUARTER_MAP`). It does a substring match against `order_date`, so it only works for records that have an `order_date` field.

**Routing**: routes are defined in `client/src/main.js` (Dashboard, Inventory, Orders, Demand, Spending, Reports). `views/Backlog.vue` exists but has no route.

**i18n and currency**:
- `useI18n` provides `t('a.b.c')` with English/Japanese locale files in `client/src/locales/{en,ja}.js`, falling back to English. The chosen locale is saved in localStorage under `app-locale`.
- The locale also sets the currency: `ja` displays JPY. `utils/currency.js` converts from USD at a fixed rate of 150. All data is stored in USD.
- When you add a UI string, add it to both locale files.

**Auth**: `useAuth.js` returns a hardcoded mock user; there is no real authentication.

**Tests**: `tests/backend/conftest.py` adds `server/` to `sys.path` and imports `main.app` into a `TestClient` fixture named `client`.

Subdirectory guides: `client/CLAUDE.md` (Vue conventions) and `server/CLAUDE.md` (FastAPI conventions).

## API Endpoints
- `GET /api/inventory`, `/api/inventory/{id}` - Filters: warehouse, category
- `GET /api/orders`, `/api/orders/{id}` - Filters: warehouse, category, status, month
- `GET /api/dashboard/summary` - All filters
- `GET /api/demand`, `/api/backlog` - No filters
- `GET /api/spending/*` - Summary, monthly, categories, transactions
- `GET /api/reports/quarterly`, `/api/reports/monthly-trends`
- `GET /api/restock/recommendations` - One row per demand forecast with suggested quantity, cost, lead time, `already_ordered`
- `GET/POST /api/tasks`, `PATCH/DELETE /api/tasks/{id}` - Header Tasks modal (in memory). IDs are strings (`TASK-0001`) so they don't collide with the numeric mock tasks from `useAuth.js`; PATCH toggles pending/completed
- `GET /api/restock-orders`, `POST /api/restock-orders` - Restocking orders (in memory). POST body `{budget, items:[{sku, quantity}]}`; server prices items, rejects over-budget (400), unknown SKU (404), already-ordered SKU (409). Lead time = slowest item's category lead time (`LEAD_TIME_DAYS` in `server/main.py`)

## Code Style
- Always document non-obvious logic changes with comments

## Common Issues
1. Use unique keys in v-for (not `index`) - use `sku`, `month`, etc.
2. Validate dates before `.getMonth()` calls
3. Update Pydantic models when changing JSON data structure
4. Inventory filters don't support month (no time dimension)
5. Revenue goals: $800K/month single, $9.6M YTD all months

## File Locations
- Views: `client/src/views/*.vue`
- API Client: `client/src/api.js`
- Backend: `server/main.py`, `server/mock_data.py`
- Data: `server/data/*.json`
- Styles: `client/src/App.vue`

## Design System
- Colors: Slate/gray (#0f172a, #64748b, #e2e8f0)
- Status: green/blue/yellow/red
- Charts: Custom SVG, CSS Grid for layouts
- No emojis in UI
