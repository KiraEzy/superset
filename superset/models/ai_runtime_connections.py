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
"""Approved MCP destinations and private, post-scoped account bindings."""

from datetime import datetime
from uuid import uuid4

from flask_appbuilder import Model
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from superset.extensions import encrypted_field_factory


class AiRuntimeConnection(Model):
    """Administrator-reviewed destination; OAuth client secrets stay encrypted."""

    __tablename__ = "ai_runtime_connection"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    label = Column(String(128), nullable=False)
    url = Column(Text, nullable=False)
    auth_type = Column(String(16), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    allow_private = Column(Boolean, nullable=False, default=False)
    reviewed_tools = Column(Text, nullable=False, default="{}")
    oauth_config = Column(encrypted_field_factory.create(Text), nullable=True)
    version = Column(Integer, nullable=False, default=1)


class AiRuntimeAccount(Model):
    """One user's credentials for exactly one post and connection."""

    __tablename__ = "ai_runtime_account"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "user_id", "post_id", name="uq_ai_runtime_account_scope"
        ),
    )
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    connection_id = Column(
        String(36),
        ForeignKey("ai_runtime_connection.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer, ForeignKey("ab_user.id", ondelete="CASCADE"), nullable=False
    )
    post_id = Column(Integer, nullable=False)
    credentials = Column(encrypted_field_factory.create(Text), nullable=False)


class AiRuntimeOAuthState(Model):
    """Single-use OAuth state with actor, post, redirect and PKCE binding."""

    __tablename__ = "ai_runtime_oauth_state"
    state = Column(String(64), primary_key=True)
    connection_id = Column(
        String(36),
        ForeignKey("ai_runtime_connection.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer, ForeignKey("ab_user.id", ondelete="CASCADE"), nullable=False
    )
    post_id = Column(Integer, nullable=False)
    verifier = Column(encrypted_field_factory.create(Text), nullable=False)
    redirect_uri = Column(Text, nullable=False)
    expires_on = Column(DateTime, nullable=False, default=datetime.utcnow)
