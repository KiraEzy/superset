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
import logging
from functools import partial
from typing import Any
from uuid import UUID

from superset.commands.ai_chat.exceptions import (
    AiChatMessageAppendFailedError,
    AiChatSessionNotFoundError,
)
from superset.commands.base import BaseCommand
from superset.daos.ai_chat import AiChatSessionDAO
from superset.models.ai_chat import AiChatMessage
from superset.utils.decorators import on_error, transaction

logger = logging.getLogger(__name__)


class AppendAiChatMessageCommand(BaseCommand):
    def __init__(self, session_uuid: UUID, data: dict[str, Any]):
        self._session_uuid = session_uuid
        self._data = data.copy()

    @transaction(on_error=partial(on_error, reraise=AiChatMessageAppendFailedError))
    def run(self) -> AiChatMessage:
        self.validate()
        session = AiChatSessionDAO.find_by_uuid(self._session_uuid)
        if not session:
            raise AiChatSessionNotFoundError()
        return AiChatSessionDAO.append_message(
            session,
            role=self._data["role"],
            content=self._data["content"],
            extra=self._data.get("extra"),
        )

    def validate(self) -> None:
        session = AiChatSessionDAO.find_by_uuid(self._session_uuid)
        if not session:
            raise AiChatSessionNotFoundError()
