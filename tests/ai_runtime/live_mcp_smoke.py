# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Read-only verification against the installed, unchanged Focal MCP service."""

import asyncio
import json

from flask import g
from flask_appbuilder.security.sqla.models import User

from superset import security_manager
from superset.app import create_app
from superset.extensions import db


def main() -> None:
    """Discover authorized tools and call health_check without model or BI writes."""
    app = create_app()
    with app.test_request_context(base_url="http://localhost:8088/"):
        from superset.ai_runtime.connections import resolve_connections
        from superset.ai_runtime.mcp import MCPPool
        from superset.views.ai.mcp_jwt import mint_mcp_user_token

        candidates = db.session.query(User).filter_by(active=True).all()
        actor = next(
            (user for user in candidates if security_manager.get_user_posts(user)), None
        )
        if actor is None:
            raise RuntimeError("No assigned test actor is available")
        post_id = security_manager.get_user_posts(actor)[0].id
        g.user, g.mcp_active_post_id = actor, post_id
        connections = resolve_connections(["focalbi"], actor.id, post_id)

        def auth():
            return mint_mcp_user_token(user=actor, active_post_id=post_id)

        async def probe():
            async with MCPPool() as pool:
                tools = await pool.discover(connections, auth)
                health = next(
                    tool for tool in tools if tool.original_name == "health_check"
                )
                result = await pool.call(health, {})
                print(
                    json.dumps(
                        {
                            "discovered_tools": len(tools),
                            "health_error": result["isError"],
                            "instructions_loaded": len(pool.instructions),
                            "server_modified": False,
                        }
                    )
                )

        asyncio.run(probe())


if __name__ == "__main__":
    main()
