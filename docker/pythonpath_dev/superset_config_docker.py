# Local dev only — do not use in production
MCP_AUTH_ENABLED = True
MCP_JWT_ALGORITHM = "HS256"
MCP_JWT_SECRET = "focal-dev-mcp-jwt-secret-change-me"
MCP_JWT_ISSUER = "focal-bi"
MCP_JWT_AUDIENCE = "superset-mcp"
# Keep for non-chat local probes only; chat must not use this when auth is on
MCP_DEV_USERNAME = "admin"

# Post-based RBAC: scope permissions to the active post selected at login.
from os import environ as _focalbi_cache_environment

from superset.security.focal_manager import FocalSecurityManager  # noqa: E402

CUSTOM_SECURITY_MANAGER = FocalSecurityManager
FOCAL_POST_RBAC_ENABLED = True

# Sync Public role with read-only dashboard/chart permissions for viewer users
PUBLIC_ROLE_LIKE = "Public"

MCP_SERVICE_HOST = "0.0.0.0"
MCP_SERVICE_PORT = 5008
MCP_SERVICE_URL = "http://localhost:5008"

# LM Studio and some MCP clients call tools by name directly; they do not use
# the call_tool proxy. Disable tool search so all tools appear in tools/list.
MCP_TOOL_SEARCH_CONFIG = {
    "enabled": False,
}

# Backend AI proxy: reach MCP + host LM Studio from inside Docker
AI_MCP_INTERNAL_URL = "http://superset_mcp:5008/mcp"
AI_DOCKER_HOST = "host.docker.internal"

# Optional local dashboard embedding, provisioned by embedded-demo/setup.ps1.
from focal_embedding import *  # noqa: E402,F403

# Links returned by MCP should open the running local web application.
WEBDRIVER_BASEURL_USER_FRIENDLY = "http://localhost:8088/"

# Query results from saved tables/datasets use a one-day Redis lifetime.
# Keep metadata, thumbnails, filter state and Explore state on their own settings.
DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 86400,
    "CACHE_KEY_PREFIX": "superset_",
    "CACHE_REDIS_HOST": _focalbi_cache_environment.get("REDIS_HOST", "redis"),
    "CACHE_REDIS_PORT": _focalbi_cache_environment.get("REDIS_PORT", "6379"),
    "CACHE_REDIS_DB": _focalbi_cache_environment.get("REDIS_RESULTS_DB", "1"),
}

# Use the native theme contract for page and chart loading in every renderer.
# Copy the native themes so their other defaults and shared objects stay intact.
from copy import deepcopy as _focalbi_theme_copy  # noqa: E402
from pathlib import Path as _focalbi_theme_path  # noqa: E402

from superset.config import THEME_DARK as _focalbi_native_dark  # noqa: E402
from superset.config import THEME_DEFAULT as _focalbi_native_default  # noqa: E402

_focalbi_spinner_svg = _focalbi_theme_path(__file__).with_name(
    "focalbi_blue_spinner.svg"
).read_text(encoding="ascii")
THEME_DEFAULT = _focalbi_theme_copy(_focalbi_native_default)
THEME_DARK = _focalbi_theme_copy(_focalbi_native_dark)
for _focalbi_theme in (THEME_DEFAULT, THEME_DARK):
    if _focalbi_theme is not None:
        _focalbi_theme["token"].update(
            {"brandSpinnerSvg": _focalbi_spinner_svg, "brandSpinnerUrl": None}
        )
