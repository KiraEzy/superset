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
"""AI chat session and message models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask_appbuilder import Model
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from superset.models.helpers import AuditMixinNullable, ExtraJSONMixin, UUIDMixin
from superset.utils.core import MediumText


class AiChatSession(AuditMixinNullable, UUIDMixin, Model):
    """A user-owned AI chat conversation thread."""

    __tablename__ = "ai_chat_session"

    id = Column(Integer, primary_key=True)
    title = Column(String(256), nullable=False, default="New chat")
    messages = relationship(
        "AiChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AiChatMessage.created_on",
    )

    def __repr__(self) -> str:
        return f"AiChatSession<{self.id}: {self.title}>"


class AiChatMessage(ExtraJSONMixin, Model):
    """A single message within an AI chat session."""

    __tablename__ = "ai_chat_message"

    id = Column(Integer, primary_key=True)
    session_id = Column(
        Integer,
        ForeignKey("ai_chat_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String(16), nullable=False)
    content = Column(MediumText(), nullable=False, default="")
    created_on = Column(DateTime, default=datetime.utcnow, nullable=False)
    session = relationship("AiChatSession", back_populates="messages")

    @property
    def data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "extra": self.extra,
            "created_on": self.created_on,
        }

    def __repr__(self) -> str:
        return f"AiChatMessage<{self.id}: {self.role}>"
