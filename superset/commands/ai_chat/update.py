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

from flask_appbuilder.models.sqla import Model

from superset.commands.ai_chat.exceptions import (
    AiChatSessionNotFoundError,
    AiChatSessionUpdateFailedError,
)
from superset.commands.base import BaseCommand
from superset.daos.ai_chat import AiChatSessionDAO
from superset.utils.decorators import on_error, transaction

logger = logging.getLogger(__name__)


class UpdateAiChatSessionCommand(BaseCommand):
    def __init__(self, session_uuid: UUID, data: dict[str, Any]):
        self._session_uuid = session_uuid
        self._properties = data.copy()
        self._model: Model | None = None

    @transaction(on_error=partial(on_error, reraise=AiChatSessionUpdateFailedError))
    def run(self) -> Model:
        self.validate()
        assert self._model is not None
        return AiChatSessionDAO.update(self._model, self._properties)

    def validate(self) -> None:
        self._model = AiChatSessionDAO.find_by_uuid(self._session_uuid)
        if not self._model:
            raise AiChatSessionNotFoundError()
