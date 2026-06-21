# Superset Local Dev Setup (Backend + Frontend)

Run the **backend in Docker** and the **frontend on the host** with hot reload — for quick UI changes.

## Prerequisites

| Tool | Version |
|------|---------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Latest (with `docker compose`) |
| [Git](https://git-scm.com/) | Any recent |
| [Node.js](https://nodejs.org/) | **20.18+** (use `nvm` / `nvm-windows`) |
| npm | **10.8+** (bundled with Node 20) |

**Docker resources:** allocate at least **8 GB RAM** and **4 CPUs** in Docker Desktop settings.

---

## 1. Get the code (match versions)

```bash
git clone https://github.com/apache/superset.git
cd superset
git checkout tags/6.0.0
```

> **Important:** Backend Docker image tag and frontend source **must match** (both `6.0.0`).

---

## 2. Pin the Docker image tag

Create `superset/.env` in the repo root (same folder as `docker-compose-image-tag.yml`):

```env
TAG=6.0.0
```

> Do **not** put `TAG` only in `docker/.env-local` — Compose reads image tags from `superset/.env`.

---

## 3. Start the backend (Docker)

From the `superset` repo root:

```bash
docker compose -f docker-compose-image-tag.yml pull
docker compose -f docker-compose-image-tag.yml up
```

First run takes several minutes (DB init + example data).

**Verify backend:**

- Health: http://localhost:8088/health
- UI (bundled assets): http://localhost:8088
- Login: `admin` / `admin`

**Stop backend:**

```bash
docker compose -f docker-compose-image-tag.yml down
```

**Reset database** (if you switched image tags and migrations fail):

```bash
docker compose -f docker-compose-image-tag.yml down -v
docker compose -f docker-compose-image-tag.yml up
```

---

## 4. Start the frontend (dev server)

Open a **second terminal**:

```bash
cd superset/superset-frontend

# Use Node 20 (example with nvm)
nvm install 20.19.0
nvm use 20.19.0

# Install dependencies (first time only)
npm ci

# Start webpack dev server
npm run dev-server
```

Wait until you see:

```
webpack compiled successfully
[HPM] Proxy created: /  -> http://localhost:8088
```

**Use the app at:** http://localhost:9000

(Log in at http://localhost:9000/login/ — same `admin` / `admin`)

> Use **`npm run dev-server`** (port 9000), not `npm run dev` (watch build only, no web server).

---

## Port summary

| URL | Purpose |
|-----|---------|
| http://localhost:9000 | **Frontend dev** (hot reload) — use this for UI work |
| http://localhost:8088 | Backend API + bundled UI (no hot reload) |

The dev server on **9000** proxies API requests to **8088** and injects local JS/CSS.

---

## Daily workflow

**Terminal 1 — backend:**

```bash
cd superset
docker compose -f docker-compose-image-tag.yml up
```

**Terminal 2 — frontend:**

```bash
cd superset/superset-frontend
nvm use 20.19.0
npm run dev-server
```

Edit files under `superset-frontend/src/` → browser refreshes automatically.

---

## Troubleshooting

### `npm ci` fails on Windows (`EACCES` / symlink error)

```powershell
cd superset\superset-frontend
Remove-Item -Recurse -Force node_modules
npm ci
```

### Blank page / `FlashProvider` crash on :9000

- Backend and frontend versions don't match → ensure `git checkout tags/6.0.0` and `TAG=6.0.0` in `superset/.env`
- Docker still on `latest-dev` → run `docker inspect superset_app --format "{{.Config.Image}}"` — should show `:6.0.0`
- Restart Docker after changing `.env`

### `npm ci` engine warning

Use Node **20.x**, not 22:

```bash
nvm use 20.19.0
```

### Backend migration error after tag switch

Reset volumes:

```bash
docker compose -f docker-compose-image-tag.yml down -v
docker compose -f docker-compose-image-tag.yml up
```

---

## Optional: proxy to a different backend port

```bash
npm run dev-server -- --env=--supersetPort=8081
```

---

## References

- [Superset quickstart](https://superset.apache.org/user-docs/quickstart/)
- [Webpack dev server (contributing docs)](https://superset.apache.org/docs/contributing/development/#webpack-dev-server)
