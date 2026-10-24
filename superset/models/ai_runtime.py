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
"""Persistent Chat execution ledger, separate from MCP server storage."""

from datetime import datetime
from uuid import uuid4

from flask_appbuilder import Model
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)

from superset.extensions import encrypted_field_factory


def new_id() -> str:
    """Generate a public UUID without depending on database sequences."""
    return str(uuid4())


def encrypted_text() -> TypeDecorator:
    """Protect tool evidence and execution snapshots at rest."""
    return encrypted_field_factory.create(Text)


class AiRuntimeTurn(Model):
    """One durable user request, optionally suspended for interaction."""

    __tablename__ = "ai_runtime_turn"
    __table_args__ = (UniqueConstraint("session_id", "idempotency_key"),)
    id = Column(String(36), primary_key=True, default=new_id)
    session_id = Column(
        Integer,
        ForeignKey("ai_chat_session.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer, ForeignKey("ab_user.id"), nullable=False)
    post_id = Column(Integer, nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    input_hash = Column(String(64), nullable=False)
    active_key = Column(String(36), nullable=True, unique=True)
    status = Column(String(24), nullable=False, default="queued", index=True)
    content = Column(encrypted_text(), nullable=False, default="")
    state_json = Column(encrypted_text(), nullable=False, default="{}")
    error_json = Column(Text, nullable=True)
    next_sequence = Column(Integer, nullable=False, default=0)
    lease_owner = Column(String(36), nullable=True)
    lease_expires = Column(DateTime, nullable=True, index=True)
    created_on = Column(DateTime, nullable=False, default=datetime.utcnow)
    changed_on = Column(DateTime, nullable=False, default=datetime.utcnow)


class AiRuntimeItem(Model):
    """A persisted message, operation, or pending interaction."""

    __tablename__ = "ai_runtime_item"
    id = Column(String(36), primary_key=True, default=new_id)
    turn_id = Column(
        String(36),
        ForeignKey("ai_runtime_turn.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind = Column(String(32), nullable=False)
    status = Column(String(24), nullable=False, default="completed")
    external_id = Column(String(256), nullable=True)
    payload_json = Column(encrypted_text(), nullable=False, default="{}")
    created_on = Column(DateTime, nullable=False, default=datetime.utcnow)


class AiRuntimeEvent(Model):
    """Ordered events committed before delivery to any subscriber."""

    __tablename__ = "ai_runtime_event"
    __table_args__ = (UniqueConstraint("turn_id", "sequence"),)
    id = Column(String(36), primary_key=True, default=new_id)
    turn_id = Column(
        String(36),
        ForeignKey("ai_runtime_turn.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id = Column(String(36), nullable=True)
    sequence = Column(Integer, nullable=False)
    event_type = Column(String(32), nullable=False)
    payload_json = Column(encrypted_text(), nullable=False, default="{}")
    created_on = Column(DateTime, nullable=False, default=datetime.utcnow)


class AiRuntimeArtifact(Model):
    """An immutable artifact version with source and execution provenance."""

    __tablename__ = "ai_runtime_artifact"
    id = Column(String(36), primary_key=True, default=new_id)
    turn_id = Column(
        String(36),
        ForeignKey("ai_runtime_turn.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    artifact_type = Column(String(24), nullable=False)
    title = Column(String(256), nullable=False, default="Result")
    version = Column(Integer, nullable=False, default=1)
    payload_json = Column(encrypted_text(), nullable=False, default="{}")
    provenance_json = Column(encrypted_text(), nullable=False, default="{}")
    created_on = Column(DateTime, nullable=False, default=datetime.utcnow)


class AiRuntimeOutbox(Model):
    """Dispatch requests committed atomically with accepted input."""

    __tablename__ = "ai_runtime_outbox"
    id = Column(String(36), primary_key=True, default=new_id)
    turn_id = Column(
        String(36),
        ForeignKey("ai_runtime_turn.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String(16), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    created_on = Column(DateTime, nullable=False, default=datetime.utcnow)
    dispatched_on = Column(DateTime, nullable=True)
