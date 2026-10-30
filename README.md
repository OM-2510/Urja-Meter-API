# Urja Meter API

A read-only FastAPI service that presents meter and consumption data from the
Urja Meter Ops Portal through a small, normalized REST API. It handles portal
login, session cookies, signed meter exports, retries, and in-memory caching.

## Project layout & Documentation

The core documentation required for this assignment lives in the `docs/` directory.

- [`docs/PROTOCOL.md`](docs/PROTOCOL.md) — Detailed write-up of how the legacy portal works under the hood (data paths, auth, quirks).
- [`docs/REFLECTION.md`](docs/REFLECTION.md) — Answers to the assignment's reflection questions (assumptions, mistakes, future improvements).
- [`docs/notes.md`](docs/notes.md) — Raw investigation notes taken during the discovery phase.
- `backend/app/` — FastAPI routes, portal client, service, and schemas.
- `backend/app/tests/` — API, client, and configuration tests.
- `backend/scripts/` — Local client utility.
- `openapi.json` — Auto-generated OpenAPI 3.x schema snapshot.
- `Dockerfile` — Container image definition.
- `compose.yaml` — Local Docker Compose service.

## Requirements

- Python 3.13 or later
- [uv](https://docs.astral.sh/uv/)
- Portal credentials with access to the Urja Meter Ops Portal

## Configuration

Copy `.env.example` to `.env` in the repository root and set the portal URL and
credentials:

```dotenv
BASE_URL=https://urja-ops.flockenergy.tech
EMAIL=your-email@example.com
PASSWORD=your-portal-password
CACHE_TTL_SECONDS=300
```

`CACHE_TTL_SECONDS` is optional and defaults to `300`. Keep `.env` private; it
is excluded from version control and Docker build contexts.

## Run locally

From the repository root:

```powershell
uv sync --directory .\backend
uv run --directory .\backend uvicorn app.main:app --reload
```

The API listens on http://127.0.0.1:8000. Interactive API documentation is
available at http://127.0.0.1:8000/docs, with the generated OpenAPI schema at http://127.0.0.1:8000/openapi.json.

## Run with Docker Compose

Docker and the Docker Compose plugin are required. Create and configure the
root `.env` file as above, then run:

```powershell
docker compose up --build
```

Compose publishes the API on 127.0.0.1:8000 and checks `/health`. To stop it:

```powershell
docker compose down
```

## API

All responses are JSON. Meter and consumption endpoints require valid portal
credentials; `/health` is a liveness check and does not contact the portal.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness status |
| `GET` | `/meters` | Filter and paginate meters |
| `GET` | `/meters/{meter_id}` | Get one meter |
| `GET` | `/meters/{meter_id}/consumption` | Get a meter's readings, optionally filtered by time |

### List meters

`GET /meters` supports these optional query parameters:

| Parameter | Description |
| --- | --- |
| `q` | Case-insensitive substring search in meter ID or serial number |
| `make` | Exact, case-insensitive make filter |
| `phase_type` | Exact, case-insensitive phase filter (for example, `single` or `three`) |
| `install_status` | Exact, case-insensitive status filter |
| `dt_code` | Exact, case-insensitive distribution-transformer code filter |
| `page` | 1-based page number (default `1`) |
| `page_size` | Results per page, from `1` to `100` (default `20`) |

Example:

```plaintext
GET /meters?make=HPL&install_status=Installed&page=1&page_size=20
```

The response contains items, the filtered total, page, and page_size.
Meter records include identifiers, installation and make details, optional
geographic coordinates, and the available electrical hierarchy.

### Meter consumption

`GET /meters/{meter_id}/consumption` accepts optional `from` and `to` ISO 8601
timestamps. Naive timestamps are interpreted as India Standard Time (IST,
UTC+05:30); portal readings are returned with that timezone. Both bounds are
inclusive. Unknown meters return `404`.

```plaintext
GET /meters/J100000/consumption?from=2026-06-30T00:00:00%2B05:30&to=2026-06-30T23:59:59%2B05:30
```

The response contains the meter ID, reading count, and readings with timestamp, `kwh`, `kvah`, and `volt_r` fields. Unavailable or unreadable numeric values
are `null`.

Portal failures are returned as `502` with an error and detail. Invalid
date ranges (`from` after `to`) return `422`.

## Data flow and limitations

- Meter details are loaded from the portal's signed `/portal/export` endpoint.
- Consumption is fetched from `/portal/meters/{meterId}/energy` when requested.
- Export data and per-meter readings are cached in process memory for the configured TTL; the cache is not shared across workers or persisted.
- The portal client signs export requests with a key fetched at runtime and retries once for an expired session or invalid signature.
- This service has no user authentication or rate limiting. Keep it on a trusted network and do not expose it directly to the public internet.
- The service depends on the portal's current authentication and signing behavior; changes to the upstream portal may require client updates.

## Tests

From the repository root:

```powershell
uv run --directory .\backend pytest
```

## AI use log

- Used Claude as a tutor to learn Chrome DevTools, to structure investigation notes, and to explain the minified signing function after extracting it from the page's JS.
- Claude suggested where to look (the Initiator tab) and supplied a generic HMAC snippet alongside candidate message formats during the initial signature discovery phase.
- Endpoint discovery, header manipulation, curl reproductions, and verifying the final signature match were done manually.
- Bulk data received from the `/portal/export`, `/portal/dts`, and `/portal/meters/{meterId}/energy` endpoints was analyzed with AI to quickly identify data patterns, types, and structural quirks.
- Tests were composed by AI to specifically target and cover edge cases left out by manual human testing.