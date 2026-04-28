# FinLens

Multi-user finance dashboard: upload bank exports (XLSX, CSV, PDF), parse transactions, optional GPT-4o analysis. Stack: **FastAPI** (async), **PostgreSQL**, **Redis** (sessions + rate limits), **Nginx** (reverse proxy + static frontend).

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with **Docker Compose v2**
- For production on a server: open the HTTP port you configure (default **80**)

## Configuration

1. Copy the environment template and edit values:

   ```bash
   cp .env.example .env
   ```

2. In **`.env`**, set strong secrets (do not commit `.env`; it is gitignored):

   | Variable | Purpose |
   |----------|---------|
   | `POSTGRES_*` | Database name, user, password |
   | `REDIS_PASSWORD` | Redis ACL password (used in `REDIS_URL` inside Compose) |
   | `SECRET_KEY` | Long random string (e.g. 64+ chars) |
   | `PEPPER` | Extra secret concatenated before password hashing |
   | `ENCRYPTION_KEY` | **Base64-encoded 32 bytes** (AES-256-GCM for stored data) |
   | `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Initial admin created on first startup |
   | `ENVIRONMENT` | `production` (cookies may use secure flags behind HTTPS) or `development` (easier on plain `http://localhost`) |
   | `HTTP_PORT` | Host port mapped to Nginx (default `80`) |

3. Generate **`ENCRYPTION_KEY`**:

   ```bash
   python3 -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
   ```

## Production

Build and run all services in the background:

```bash
docker compose up -d --build
```

- **App (via Nginx):** `http://localhost` — or `http://<your-server>` if you deploy remotely (use the port from `HTTP_PORT`).
- **Health check:** `curl http://localhost/health` → `{"status":"ok"}` (proxied to the backend).
- **Logs:** `docker compose logs -f backend`

Stop containers (keeps the Postgres volume):

```bash
docker compose down
```

**Reset the database** (destructive — deletes all data):

```bash
docker compose down -v
```

Then start again with `docker compose up -d --build`.

### First login

Use **`ADMIN_USERNAME`** and **`ADMIN_PASSWORD`** from `.env`. If no admin row exists yet, the backend creates one during startup.

## Development

### Option A — Full stack in Docker (simplest)

Run in the foreground to see logs from all services:

```bash
docker compose up --build
```

Press `Ctrl+C` to stop. After changing **backend** code, rebuild that service:

```bash
docker compose up --build backend
```

The **frontend** is mounted read-only from `./frontend`; refresh the browser after editing HTML/CSS/JS (no rebuild needed for static files). Nginx may cache aggressively for `/static/`; hard-refresh or bump asset URLs if you do not see changes.

### Option B — Backend on the host (advanced)

The default `docker-compose.yml` does **not** publish Postgres or Redis on the host. To run **Uvicorn** locally you can:

1. Add `ports` to the `db` and `redis` services (e.g. `5432:5432`, `6379:6379`) in a local override file, **or** run Postgres/Redis however you prefer.
2. Set `DATABASE_URL` and `REDIS_URL` in your shell or a local `.env` to point at those instances (same variable names the app expects: `postgresql+asyncpg://...`, `redis://:password@host:6379/0`).
3. From the **`backend/`** directory:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

The SPA is built for **same-origin** API calls (`/api/...` through Nginx). If you only run the API on `localhost:8000`, open the UI from that origin or add a dev proxy/CORS — the production image does not enable broad CORS.

## Project layout (high level)

```
finlens/
├── docker-compose.yml
├── .env.example
├── backend/app/          # FastAPI app, routers, services, models
├── frontend/             # index.html, dashboard.html, admin.html, static/
├── nginx/nginx.conf
└── postgres/init.sql     # initial schema + seed settings rows
```

## Troubleshooting

| Issue | What to try |
|--------|-------------|
| `Cannot connect to the Docker daemon` | Start **Docker Desktop** (or your engine) and retry. |
| Backend exits on startup / DB errors | Ensure `db` healthcheck passes; check `docker compose logs db backend`. |
| Blank page or 502 | Confirm `backend` is running: `docker compose ps` and `docker compose logs nginx backend`. |
| Cookies / login on `http://localhost` | Set `ENVIRONMENT=development` in `.env` if secure cookies block the session. |

