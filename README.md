# StudentHub MCP — read-only data layer

Agent-facing MCP server exposing the StudentHub recruitment database as
read-only tools. Built for the BAWES agent fleet (recruitment, outreach,
interview coordination) — **no write tools, no mutations, ever**.

## Safety contract

- **SELECT-only.** Every tool is a parameterized SELECT. There are no write
  tools, no DDL, no mutations of any kind.
- **Hard limits.** Every collection query caps at 200 rows (default 50).
- **Defense in depth (prod).** The server is read-only AND is designed to run
  against a dedicated `mcp_reader` MySQL user (SELECT-only grant), so even a
  server bug or compromise cannot modify prod data.
- **Dev-clone first.** All development and testing happens against the local
  MySQL dev clone (`studenthub_prod_local`), never prod. Prod is only touched
  after explicit approval, using the read-only user.

## Tools

| Tool | Purpose |
|---|---|
| `search_candidates` | Filter candidates by name/email/phone, country, university, skill, status |
| `get_candidate_profile` | Full profile: contact, skills, education, work history, links |
| `search_requests` | Hiring pipeline: status, company, position, dates |
| `get_request` | Full request: position, company, applications (candidates), timeline |
| `get_companies` | Companies with parent/sub-company relationship |
| `get_company_tree` | Company hierarchy: parent + sub-companies (for rate/invoice aggregation) |
| `get_universities` | University reference with candidate counts |
| `get_countries` | Country distribution of the candidate pool |
| `resolve_person` | **Layer 2 identity registry** — resolve any identifier (Discord id, Universe player id, email, phone) to a person + their linked player accounts + legacy StudentHub identities |

## Person registry (Layer 2)

Cross-platform identity: one `person` row per human, linking Discord / Universe
player ids / email / phone to legacy StudentHub account ids. Additive and
reversible — `migrations/001_person_registry.sql` creates 3 new tables and
touches no legacy table. Applied to prod **manually after approval**; the MCP
itself is SELECT-only and never runs DDL.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
# .env with SH_DB_HOST, SH_DB_PORT, SH_DB_USER, SH_DB_PASSWORD, SH_DB_NAME
.venv/bin/python server.py        # serves on :8000, /health + /mcp
.venv/bin/python probe.py         # end-to-end handshake + tool calls
```

Health: `GET http://127.0.0.1:8000/health` → `{"status":"ok","read_only":true}`

## Schema notes (verified against dev clone of prod, 2026-08-11)

- Legacy Yii2 DB: UUID primary keys (`request_uuid`, `application_uuid`),
  snake_case columns, country/university referenced via FK ids.
- `candidate_country` does NOT exist — join `country` via `candidate.country_id`.
- `request_candidate` does NOT exist — it's `request_application`.
- `request_interview` is vestigial (0 rows); `fulltimer` is legacy/stale and
  deliberately NOT exposed — it doesn't fit the universal people model.
- Phone numbers are partially masked *in the source data itself* (e.g.
  `+965****3854`) for some candidates — not a bug in this server.
- Status enums (verified): `request.request_status` ∈
  cancelled(1604) / delivered(929) / finished_by_recruitment(171) / started(1) /
  re_work(1). There is NO `pending` status in current data.

## Roadmap

- Phase 2 (finance): transfers, invoices + sub-company aggregation, contracts,
  rates — aggregation logic lifted from codex `finance/actions.ts`.
- Phase 3: story/invitation funnel (recruiter velocity), staff ops, stores.
- Phase 4: email/marketing, engagement.
