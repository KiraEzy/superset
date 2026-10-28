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
        if self._model.runtime_version == 2:
            from superset.ai_runtime.native_session import application_models
            from superset.extensions import db

            session, item = application_models()
            identifier = str(self._model.uuid)
            row = (
                db.session.query(session)
                .filter_by(
                    id=identifier,
                    owner_id=self._model.created_by_fk,
                    post_id=self._model.post_id,
                )
                .one_or_none()
            )
            if row is not None:
                db.session.query(session.summary_model).filter_by(
                    session_id=identifier
                ).delete()
                db.session.query(item).filter_by(session_id=identifier).delete()
                db.session.delete(row)
        AiChatSessionDAO.delete([self._model])

    def validate(self) -> None:
        self._model = AiChatSessionDAO.find_by_uuid(self._session_uuid)
        if not self._model:
            raise AiChatSessionNotFoundError()
