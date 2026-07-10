# Local dev only — do not use in production
MCP_AUTH_ENABLED = True
MCP_JWT_ALGORITHM = "HS256"
MCP_JWT_SECRET = "focal-dev-mcp-jwt-secret-change-me"
MCP_JWT_ISSUER = "focal-bi"
MCP_JWT_AUDIENCE = "superset-mcp"
# Keep for non-chat local probes only; chat must not use this when auth is on
MCP_DEV_USERNAME = "admin"

# Post-based RBAC: scope permissions to the active post selected at login.
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
