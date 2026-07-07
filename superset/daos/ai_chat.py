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
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from superset.ai_chat.filters import AiChatSessionFilter
from superset.daos.base import BaseDAO
from superset.extensions import db
from superset.models.ai_chat import AiChatMessage, AiChatSession
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)


class AiChatSessionDAO(BaseDAO[AiChatSession]):
    model_cls = AiChatSession
    base_filter = AiChatSessionFilter

    @classmethod
    def find_by_uuid(cls, session_uuid: UUID) -> AiChatSession | None:
        query = (
            db.session.query(AiChatSession)
            .options(joinedload(AiChatSession.messages))
            .filter(AiChatSession.uuid == session_uuid)
        )
        query = cls._apply_base_filter(query)
        return query.one_or_none()

    @classmethod
    def append_message(
        cls,
        session: AiChatSession,
        *,
        role: str,
        content: str,
        extra: dict[str, Any] | None = None,
    ) -> AiChatMessage:
        message = AiChatMessage(
            session_id=session.id,
            role=role,
            content=content,
        )
        if extra:
            message.extra = extra
        db.session.add(message)
        # Order history by last user activity, not assistant replies or session reads.
        if role == "user":
            session.changed_on = message.created_on
            db.session.add(session)
        return message
