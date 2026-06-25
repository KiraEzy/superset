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
from typing import Optional
from uuid import UUID

from superset.commands.ai_chat.exceptions import (
    AiChatSessionDeleteFailedError,
    AiChatSessionNotFoundError,
)
from superset.commands.base import BaseCommand
from superset.daos.ai_chat import AiChatSessionDAO
from superset.models.ai_chat import AiChatSession
from superset.utils.decorators import on_error, transaction

logger = logging.getLogger(__name__)


class DeleteAiChatSessionCommand(BaseCommand):
    def __init__(self, session_uuid: UUID):
        self._session_uuid = session_uuid
        self._model: Optional[AiChatSession] = None

    @transaction(on_error=partial(on_error, reraise=AiChatSessionDeleteFailedError))
    def run(self) -> None:
        self.validate()
        assert self._model is not None
        AiChatSessionDAO.delete([self._model])

    def validate(self) -> None:
        self._model = AiChatSessionDAO.find_by_uuid(self._session_uuid)
        if not self._model:
            raise AiChatSessionNotFoundError()
