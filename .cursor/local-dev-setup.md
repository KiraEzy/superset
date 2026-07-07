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

Then [re-apply Tableau-like license roles](#re-apply-after-reset) if you use the `creator` / `explorer` / `viewer` test accounts.

### After reverting (git checkout, reset, or branch switch)

Old containers and volumes can conflict with the reverted code. **Remove all Superset-related containers** (including leftovers from `docker-compose.yml` if you used the source build), then reset and start the image-tag stack:

```powershell
cd superset

# Stop/remove containers from the source compose stack (if any)
docker compose down -v

# Stop/remove the image-tag stack and volumes
docker compose -f docker-compose-image-tag.yml down -v

# Remove any stopped containers still holding shared volumes (e.g. superset-node)
docker ps -a --filter "name=superset" --format "{{.Names}}"
# docker rm <container-name>   # if down -v warns "Resource is still in use"

# Fresh start
docker compose -f docker-compose-image-tag.yml up -d
```

If `down -v` reports `superset_superset_home` is still in use, a stopped container (often `superset-superset-node-1`) is referencing it — remove that container, then run `down -v` again or `docker volume rm superset_superset_home`.

Reinstall frontend dependencies if `package.json` or lockfile changed:

```powershell
cd superset-frontend
Remove-Item -Recurse -Force node_modules -ErrorAction SilentlyContinue
npm ci
npm install "@react-spring/web@^9.4.5" "@fontsource/inter@^5.2.6" "remark-gfm@^3.0.1" "@deck.gl/widgets@~9.2.5" "react-ace@^10.1.0" "ace-builds@^1.41.0"
```

After a database reset, also re-apply [Tableau-like license roles](#tableau-like-license-roles-dev-test-users) (custom roles and test users are not recreated by migrations alone).

---

## Tableau-like license roles (dev test users)

Focal BI maps [Tableau Creator / Explorer / Viewer](https://www.tableau.com/zh-tw/pricing/tableau-license-types) tiers to Superset roles for local RBAC testing.

| User | Password | Superset role(s) | Tableau equivalent |
|------|----------|------------------|--------------------|
| `creator` | `creator` | **Alpha** + **sql_lab** | Creator — data prep + authoring |
| `explorer` | `explorer` | **Explorer** (custom) | Explorer — build from shared sources |
| `viewer` | `viewer` | **Viewer** (custom) | Viewer — consume dashboards only |

**What each tier can do (approximate):**

| Capability | creator | explorer | viewer |
|------------|:-------:|:--------:|:------:|
| SQL Lab | ✓ | ✗ | ✗ |
| Datasets menu | ✓ | ✗ | ✗ |
| Create charts/dashboards | ✓ | ✓ | ✗ |
| Browse dashboards | ✓ | ✓ | ✓ |
| Charts menu / Explore editor | ✓ | ✓ | ✗ |
| User/role admin | ✗ | ✗ | ✗ |

**Viewer role** is cloned from Public with **Home** and **Dashboards** menus only (no Charts). It keeps Public’s dashboard consumption permissions (`can_dashboard`, `can_slice`, `can_explore_json`, filter state, datasource metadata for embedded charts) plus `can_recent_activity` on Log for the home page. Explore, Dataset, and form-data permissions are explicitly stripped so `/explore/` is blocked.

Test at http://localhost:9000 — log out, then sign in as each user (password = username).

### Re-apply after reset

Custom roles, user assignments, and examples `database_access` are **lost** when you wipe the database (`docker compose … down -v`) or run `superset init` without re-running the setup scripts. Re-apply them as follows.

#### Option A — Automatic (fresh Docker init with examples)

If you use the source Docker stack with examples loaded (`SUPERSET_LOAD_EXAMPLES=yes`), [`docker-init.sh`](../docker/docker-init.sh) runs the setup automatically after `superset init` and `load_examples`.

```powershell
cd superset
docker compose down -v
docker compose up
```

Wait for the init container to finish, then verify roles:

```powershell
docker exec superset_db psql -U superset -d superset -c "SELECT u.username, string_agg(r.name, ', ' ORDER BY r.name) AS roles FROM ab_user u JOIN ab_user_role ur ON u.id=ur.user_id JOIN ab_role r ON ur.role_id=r.id WHERE u.username IN ('creator','explorer','viewer') GROUP BY u.username;"
```

Expected output:

| username | roles |
|----------|-------|
| creator | Alpha, sql_lab |
| explorer | Explorer |
| viewer | Viewer |

#### Option B — Manual (existing running stack)

Run this after any reset, `superset init`, or when test users cannot see example dashboards:

```powershell
docker exec superset_app bash -c "superset shell <<'PYEOF'
from setup_tableau_license_roles import setup_tableau_license_roles
from grant_examples_db_access import grant_examples_database_access

setup_tableau_license_roles()
grant_examples_database_access()
print('Tableau license roles applied.')
PYEOF
"
```

If test users do not exist yet, create them in the Superset UI (**Settings → List Users**) or via `superset fab create-user`, then run the command again so `assign_tableau_users()` can attach roles.

#### Reset passwords (optional)

If login fails after a reset:

```powershell
docker exec superset_app superset fab reset-password --username creator --password creator
docker exec superset_app superset fab reset-password --username explorer --password explorer
docker exec superset_app superset fab reset-password --username viewer --password viewer
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

### `superset-worker` / `superset-worker-beat` crash with `No module named 'psycopg2'`

Docker bootstrap installs PostgreSQL drivers for the app container only, not workers. This repo adds `psycopg2-binary` in [`docker/requirements-local.txt`](../docker/requirements-local.txt). Restart workers after changing that file:

```powershell
docker compose -f docker-compose-image-tag.yml restart superset-worker superset-worker-beat
```

### Backend migration error after tag switch

Reset volumes:

```bash
docker compose -f docker-compose-image-tag.yml down -v
docker compose -f docker-compose-image-tag.yml up
```

Then [re-apply Tableau-like license roles](#re-apply-after-reset) for dev test users.

---

## Optional: proxy to a different backend port

```bash
npm run dev-server -- --env=--supersetPort=8081
```

---

## References

- [Superset quickstart](https://superset.apache.org/user-docs/quickstart/)
- [Webpack dev server (contributing docs)](https://superset.apache.org/docs/contributing/development/#webpack-dev-server)
