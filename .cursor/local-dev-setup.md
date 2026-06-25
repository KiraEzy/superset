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

# Install peer dependencies not pulled in by npm ci
npm install "@react-spring/web@^9.4.5" "@fontsource/inter@^5.2.6" "remark-gfm@^3.0.1" "@deck.gl/widgets@~9.2.5" "react-ace@^10.1.0" "ace-builds@^1.41.0"

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

### Access from other devices on your Wi‑Fi (LAN)

The dev server binds to **all interfaces** (`0.0.0.0:9000`) by default. On the dev machine, find your LAN IP (e.g. `192.168.11.122`) and open:

`http://<your-lan-ip>:9000/`

Other devices on the same network can use the same URL. API calls are proxied to the backend on this machine (`localhost:8088`), so Docker does not need to be exposed to the LAN.

- Log in again when using the LAN IP — cookies from `localhost` do not apply to `192.168.x.x`.
- If another device cannot connect, allow inbound TCP **9000** in Windows Firewall on the dev machine.
- For loopback-only access, set `WEBPACK_DEVSERVER_HOST=127.0.0.1` before `npm run dev-server`.

---

## Troubleshooting

### `npm ci` fails on Windows (`EACCES` / symlink error)

```powershell
cd superset\superset-frontend
Remove-Item -Recurse -Force node_modules
npm ci
npm install "@react-spring/web@^9.4.5" "@fontsource/inter@^5.2.6" "remark-gfm@^3.0.1" "@deck.gl/widgets@~9.2.5" "react-ace@^10.1.0" "ace-builds@^1.41.0"
```

### Webpack `Module not found` errors (`@react-spring/web`, `@fontsource/inter`, etc.)

`npm ci` does not install peer dependencies. Run the install step from section 4 after `npm ci`:

```powershell
cd superset\superset-frontend
npm install "@react-spring/web@^9.4.5" "@fontsource/inter@^5.2.6" "remark-gfm@^3.0.1" "@deck.gl/widgets@~9.2.5" "react-ace@^10.1.0" "ace-builds@^1.41.0"
```

Then restart the dev server.

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
