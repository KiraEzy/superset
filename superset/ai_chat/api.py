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
"""AI chat session REST API."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from flask import request, Response
from flask_appbuilder.api import expose, protect, safe
from flask_appbuilder.models.sqla.interface import SQLAInterface
from marshmallow import ValidationError
from sqlalchemy.orm import Query

from superset.ai_chat.filters import AiChatSessionFilter
from superset.ai_chat.schemas import (
    AiChatMessagePostSchema,
    AiChatSessionPostSchema,
    AiChatSessionPutSchema,
    AiChatSessionResponseSchema,
    AiChatSessionSummarySchema,
    openapi_spec_methods_override,
)
from superset.commands.ai_chat.append_message import AppendAiChatMessageCommand
from superset.commands.ai_chat.create import CreateAiChatSessionCommand
from superset.commands.ai_chat.delete import DeleteAiChatSessionCommand
from superset.commands.ai_chat.exceptions import (
    AiChatMessageAppendFailedError,
    AiChatSessionCreateFailedError,
    AiChatSessionDeleteFailedError,
    AiChatSessionNotFoundError,
    AiChatSessionUpdateFailedError,
)
from superset.commands.ai_chat.update import UpdateAiChatSessionCommand
from superset.constants import MODEL_API_RW_METHOD_PERMISSION_MAP, RouteMethod
from superset.daos.ai_chat import AiChatSessionDAO
from superset.extensions import db, event_logger
from superset.models.ai_chat import AiChatSession
from superset.views.base_api import BaseSupersetModelRestApi, requires_json, statsd_metrics

logger = logging.getLogger(__name__)


def session_to_dict(
    session: AiChatSession, *, include_messages: bool = False
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": session.id,
        "uuid": str(session.uuid),
        "title": session.title,
        "is_pinned": session.is_pinned,
        "created_on": session.created_on,
        "changed_on": session.changed_on,
        "runtime_version": session.runtime_version,
        "post_id": session.post_id,
        "profile_id": session.profile_id,
        "active_turn": None,
        "latest_turn": None,
    }
    if session.runtime_version == 2:
        from superset.models.ai_runtime import AiRuntimeTurn
        active = db.session.query(AiRuntimeTurn).filter_by(active_key=str(session.uuid)).first()
        if active:
            data["active_turn"] = {"id": active.id, "status": active.status}
        latest = db.session.query(AiRuntimeTurn).filter_by(session_id=session.id).order_by(AiRuntimeTurn.created_on.desc()).first()
        if latest:
            data["latest_turn"] = {"id": latest.id, "status": latest.status}
            from superset.ai_runtime.store import loads
            data["model_id"] = loads(latest.state_json).get("config", {}).get("model_id")
    if include_messages:
        data["messages"] = [message.data for message in session.messages]
        if session.runtime_version == 2:
            from superset.ai_runtime.store import work_activity
            from superset.models.ai_runtime import AiRuntimeItem
            turns = db.session.query(AiRuntimeTurn).filter_by(session_id=session.id).all()
            items = db.session.query(AiRuntimeItem).filter(AiRuntimeItem.turn_id.in_([turn.id for turn in turns])).order_by(AiRuntimeItem.created_on).all()
            grouped: dict[str, list[AiRuntimeItem]] = {}
            for item in items:
                grouped.setdefault(item.turn_id, []).append(item)
            activity = {turn.id: work_activity(turn, grouped.get(turn.id, [])) for turn in turns}
            for message in data["messages"]:
                extra = dict(message.get("extra") or {})
                identifier = extra.get("runtime_turn_id")
                if message["role"] == "assistant" and identifier in activity:
                    message["extra"] = {**extra, "activity": activity[identifier]}
    return data


class AiChatSessionInterface(SQLAInterface):
    """Keep pinned conversations before recent conversations before pagination."""

    def apply_order_by(self, query: Query, *args: Any, **kwargs: Any) -> Query:
        return super().apply_order_by(
            query.order_by(AiChatSession.is_pinned.desc()), *args, **kwargs
        )


class AiChatSessionRestApi(BaseSupersetModelRestApi):
    datamodel = AiChatSessionInterface(AiChatSession)
    resource_name = "ai_chat_session"
    allow_browser_login = True
    class_permission_name = "AiChatSession"
    method_permission_name = {
        **MODEL_API_RW_METHOD_PERMISSION_MAP,
        "append_message": "write",
    }

    include_route_methods = {
        RouteMethod.GET_LIST,
        RouteMethod.INFO,
        "get",
        "post",
        "put",
        "delete",
        "append_message",
    }

    list_columns = [
        "id",
        "uuid",
        "title",
        "is_pinned",
        "created_on",
        "changed_on",
        "changed_on_delta_humanized",
    ]
    list_select_columns = list_columns + ["created_by_fk", "changed_by_fk"]
    show_columns = list_columns
    base_order = ("changed_on", "desc")
    base_filters = [["id", AiChatSessionFilter, lambda: []]]

    add_model_schema = AiChatSessionPostSchema()
    edit_model_schema = AiChatSessionPutSchema()
    show_model_schema = AiChatSessionResponseSchema()
    list_model_schema = AiChatSessionSummarySchema()
    message_post_schema = AiChatMessagePostSchema()

    openapi_spec_tag = "AI Chat Sessions"
    openapi_spec_methods = openapi_spec_methods_override
    openapi_spec_component_schemas = (
        AiChatSessionPostSchema,
        AiChatSessionPutSchema,
        AiChatSessionResponseSchema,
        AiChatSessionSummarySchema,
        AiChatMessagePostSchema,
    )

    def _get_session_by_uuid(self, session_uuid: str) -> AiChatSession | None:
        try:
            parsed_uuid = UUID(session_uuid)
        except (ValueError, TypeError):
            return None
        session = AiChatSessionDAO.find_by_uuid(parsed_uuid)
        if session:
            db.session.refresh(session)
        return session

    @expose("/<session_uuid>", methods=("GET",))
    @protect()
    @safe
    @statsd_metrics
    @event_logger.log_this_with_context(
        action=lambda self, *args, **kwargs: f"{self.__class__.__name__}.get",
        log_to_statsd=False,
    )
    def get(self, session_uuid: str) -> Response:
        session = self._get_session_by_uuid(session_uuid)
        if not session:
            return self.response_404()
        return self.response(200, result=session_to_dict(session, include_messages=True))

    @expose("/", methods=("POST",))
    @protect()
    @safe
    @statsd_metrics
    @requires_json
    @event_logger.log_this_with_context(
        action=lambda self, *args, **kwargs: f"{self.__class__.__name__}.post",
        log_to_statsd=False,
    )
    def post(self) -> Response:
        try:
            data = self.add_model_schema.load(request.json or {})
            session = CreateAiChatSessionCommand(data).run()
            return self.response(201, id=session.id, result=session_to_dict(session))
        except ValidationError as ex:
            return self.response_422(message=ex.messages)
        except AiChatSessionCreateFailedError as ex:
            logger.error("Error creating AI chat session: %s", ex, exc_info=True)
            return self.response_422(message=str(ex))

    @expose("/<session_uuid>", methods=("PUT",))
    @protect()
    @safe
    @statsd_metrics
    @requires_json
    @event_logger.log_this_with_context(
        action=lambda self, *args, **kwargs: f"{self.__class__.__name__}.put",
        log_to_statsd=False,
    )
    def put(self, session_uuid: str) -> Response:
        try:
            data = self.edit_model_schema.load(request.json or {})
            session = UpdateAiChatSessionCommand(UUID(session_uuid), data).run()
            return self.response(200, result=session_to_dict(session))
        except ValidationError as ex:
            return self.response_422(message=ex.messages)
        except AiChatSessionNotFoundError:
            return self.response_404()
        except (ValueError, TypeError):
            return self.response_404()
        except AiChatSessionUpdateFailedError as ex:
            logger.error("Error updating AI chat session: %s", ex, exc_info=True)
            return self.response_422(message=str(ex))

    @expose("/<session_uuid>", methods=("DELETE",))
    @protect()
    @safe
    @statsd_metrics
    @event_logger.log_this_with_context(
        action=lambda self, *args, **kwargs: f"{self.__class__.__name__}.delete",
        log_to_statsd=False,
    )
    def delete(self, session_uuid: str) -> Response:
        try:
            session = self._get_session_by_uuid(session_uuid)
            if session and session.runtime_version == 2:
                from superset.models.ai_runtime import AiRuntimeTurn
                if db.session.query(AiRuntimeTurn).filter_by(active_key=str(session.uuid)).first():
                    return self.response(409, message="Stop the active turn before deleting this conversation")
            DeleteAiChatSessionCommand(UUID(session_uuid)).run()
            return self.response(200, message="OK")
        except AiChatSessionNotFoundError:
            return self.response_404()
        except (ValueError, TypeError):
            return self.response_404()
        except AiChatSessionDeleteFailedError as ex:
            logger.error("Error deleting AI chat session: %s", ex, exc_info=True)
            return self.response_422(message=str(ex))

    @expose("/<session_uuid>/message/", methods=("POST",))
    @protect()
    @safe
    @statsd_metrics
    @requires_json
    @event_logger.log_this_with_context(
        action=lambda self, *args, **kwargs: f"{self.__class__.__name__}.append_message",
        log_to_statsd=False,
    )
    def append_message(self, session_uuid: str) -> Response:
        try:
            session = self._get_session_by_uuid(session_uuid)
            if session and session.runtime_version == 2:
                return self.response(409, message="Runtime conversations accept input through the turns API")
            data = self.message_post_schema.load(request.json or {})
            message = AppendAiChatMessageCommand(UUID(session_uuid), data).run()
            session = self._get_session_by_uuid(session_uuid)
            return self.response(
                201,
                result={
                    "message": message.data,
                    "session": session_to_dict(session) if session else None,
                },
            )
        except ValidationError as ex:
            return self.response_422(message=ex.messages)
        except AiChatSessionNotFoundError:
            return self.response_404()
        except (ValueError, TypeError):
            return self.response_404()
        except AiChatMessageAppendFailedError as ex:
            logger.error("Error appending AI chat message: %s", ex, exc_info=True)
            return self.response_422(message=str(ex))
