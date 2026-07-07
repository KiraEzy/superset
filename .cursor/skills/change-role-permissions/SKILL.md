---
name: change-role-permissions
description: Add or remove permissions on a Superset role (Admin, Alpha, Gamma, Explorer, Viewer, etc.) in this Docker-based FocalBI stack. Use when the user asks to grant, revoke, or change a role's permission list, fix a "redirects to welcome"/403 access issue for a role, or make a page/menu/API reachable for a specific role.
disable-model-invocation: true
---

# Change Role Permissions (Superset / FocalBI)

Superset's MCP server has **no** tool for editing role permission lists. Change
permissions through Superset's `security_manager` inside the running container,
then verify in Postgres.

## Key facts

- A permission is a `(permission_name, view_menu_name)` pair, e.g. `("can_chat", "AI")`.
- The Superset CLI lives at `/app/.venv/bin/superset` inside `superset_app`
  (plain `superset` / `python` on PATH fails with `ModuleNotFoundError`).
- Custom roles here (`Viewer`, `Explorer`) are rebuilt by
  `docker/pythonpath_dev/setup_tableau_license_roles.py`. For those roles, edit
  the script so changes survive re-runs; for built-in roles a one-off shell is fine.

## Workflow

```
- [ ] 1. Identify the exact (permission, view_menu) pair needed
- [ ] 2. Apply change via security_manager in superset_app
- [ ] 3. Verify in Postgres
- [ ] 4. Restart app if code/permission model changed; user re-logs in
```

### 1. Find the right (permission, view_menu) pair

A route's requirement comes from its view: `class_permission_name` +
`@permission_name(...)` (or `method_permission_name` on APIs). Example:
`UserInfoView` has `class_permission_name = "user"` and `@permission_name("read")`,
so the pair is `("can_read", "user")`.

Grep the view to confirm before granting:

```bash
rg "class_permission_name|permission_name|method_permission_name" superset/superset/views/<area>
```

### 2a. Persist changes for custom roles (preferred)

For `Viewer`/`Explorer`, add the pair in
`docker/pythonpath_dev/setup_tableau_license_roles.py`:

- Grant to Viewer: add to `VIEWER_EXTRA_PERMISSIONS`.
- Allow a `can_write` on Viewer: also add the view_menu to `VIEWER_ALLOWED_WRITE_VIEW_MENUS` (Viewer strips writes otherwise).
- Share a permission across standard roles: add to `AI_CHAT_BASE_PERMISSIONS` / `AI_CHAT_STANDARD_ROLES` style helpers.

Then re-run the script:

```bash
docker exec superset_app bash -lc "cd /app && /app/.venv/bin/superset shell <<'PYEOF'
from setup_tableau_license_roles import setup_tableau_license_roles
setup_tableau_license_roles()
print('roles refreshed')
PYEOF"
```

### 2b. Ad-hoc add/remove (built-in roles or quick fix)

```bash
docker exec superset_app bash -lc "cd /app && /app/.venv/bin/superset shell <<'PYEOF'
from superset import security_manager
from superset.extensions import db

role = security_manager.find_role('Gamma')

# ADD: create the pvm if missing, then attach to role
pvm = security_manager.add_permission_view_menu('can_chat', 'AI')
security_manager.add_permission_role(role, pvm)

# REMOVE: look up existing pvm, then detach
pvm = security_manager.find_permission_view_menu('can_chat', 'AI')
if pvm:
    security_manager.del_permission_role(role, pvm)

db.session.commit()
print('done')
PYEOF"
```

- Add uses `add_permission_view_menu` (idempotent) + `add_permission_role`.
- Remove uses `find_permission_view_menu` + `del_permission_role`.
- Always `db.session.commit()`.

### 3. Verify in Postgres

```bash
docker exec superset_db psql -U superset -d superset -c "SELECT p.name AS perm, v.name AS view FROM ab_permission p JOIN ab_permission_view pv ON pv.permission_id=p.id JOIN ab_view_menu v ON v.id=pv.view_menu_id JOIN ab_permission_view_role pvr ON pvr.permission_view_id=pv.id JOIN ab_role r ON r.id=pvr.role_id WHERE r.name='Gamma' ORDER BY v.name, p.name;"
```

### 4. Restart and re-login

- Permission-only DB change: no restart, but the user must **log out and back in** (permissions are cached in the session).
- Changed view code (`class_permission_name`, decorators): `docker restart superset_app superset_mcp`.

## Gotchas

- Missing menu link but page 403s → grant both the `menu_access` pair AND the page's `can_read`/action pair.
- Viewer/Public strip `can_write` unless the view_menu is allow-listed.
- `find_role`/`find_permission_view_menu` return `None` if the name is wrong — check spelling before assuming a bug.
- Roles are re-derived on `superset init`; only script-based changes persist.
