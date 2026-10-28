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
"""Chat model catalogue and private image storage; independent of MCP."""

from datetime import datetime

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

from superset.models.ai_runtime import encrypted_text, new_id


class AiModelConnection(Model):
    """A named administrator-owned model endpoint with encrypted configuration."""

    __tablename__ = "ai_model_connection"
    id = Column(String(36), primary_key=True, default=new_id)
    label = Column(String(128), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    config_json = Column(encrypted_text(), nullable=False)


class AiModel(Model):
    """A discovered model identity and revision-bound capability verification."""

    __tablename__ = "ai_model"
    __table_args__ = (UniqueConstraint("connection_id", "model_name"),)
    id = Column(String(36), primary_key=True, default=new_id)
    connection_id = Column(
        String(36), ForeignKey("ai_model_connection.id"), nullable=False
    )
    model_name = Column(String(256), nullable=False)
    revision = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False, default="discovered")
    vision = Column(Boolean, nullable=False, default=False)
    available = Column(Boolean, nullable=False, default=True)
    position = Column(Integer, nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)
    runtime_settings_json = Column(Text, nullable=True, default="{}")
    settings_revision = Column(Integer, nullable=False, default=0)


class AiModelVerification(Model):
    """Durable bounded verification work; candidate credentials remain private."""

    __tablename__ = "ai_model_verification"
    id = Column(String(36), primary_key=True, default=new_id)
    connection_id = Column(String(36), nullable=False)
    expected_revision = Column(Integer, nullable=False)
    candidate_json = Column(encrypted_text(), nullable=False)
    kind = Column(String(16), nullable=False)
    model_id = Column(String(36), nullable=True)
    status = Column(String(24), nullable=False, default="queued")
    message = Column(Text, nullable=False, default="Queued")
    created_on = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_on = Column(DateTime, nullable=True)


class AiChatImage(Model):
    """Validated metadata-free image, encrypted in the shared metadata database."""

    __tablename__ = "ai_chat_image"
    id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(Integer, ForeignKey("ab_user.id"), nullable=False)
    post_id = Column(Integer, nullable=False)
    filename = Column(String(128), nullable=False)
    mime = Column(String(32), nullable=False)
    data = Column(encrypted_text(), nullable=False)
    bound = Column(Boolean, nullable=False, default=False)
    created_on = Column(DateTime, nullable=False, default=datetime.utcnow)
