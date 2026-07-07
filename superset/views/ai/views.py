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
from flask_appbuilder import expose, has_access, permission_name

from superset import event_logger
from superset.superset_typing import FlaskResponse
from superset.views.base import BaseSupersetView


class AIView(BaseSupersetView):
    route_base = "/ai"
    class_permission_name = "AI"

    @expose("/")
    @has_access
    @permission_name("chat")
    @event_logger.log_this
    def index(self) -> FlaskResponse:
        return super().render_app_template()


class AIConnectionView(BaseSupersetView):
    """Admin-configurable global AI connection settings page.

    Gated by the dedicated ``AIConnectionConfig`` permission (shared with the
    config REST API) so it is only reachable by permitted users.
    """

    route_base = "/ai/connection"
    class_permission_name = "AIConnectionConfig"

    @expose("/")
    @has_access
    @permission_name("read")
    @event_logger.log_this
    def index(self) -> FlaskResponse:
        return super().render_app_template()
