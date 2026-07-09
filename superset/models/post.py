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
"""Post entity models for the User -> Post -> Role -> Permission RBAC model.

A ``Post`` is a first-class named position (e.g. "Finance Analyst"). Users are
assigned to Posts and Posts are granted Roles. At login a user picks a single
Post to act as; the roles of that active Post are the only roles that grant
permissions for the session. This is intentionally distinct from FAB Groups.
"""

from __future__ import annotations

from flask_appbuilder import Model
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import backref, relationship

from superset.models.helpers import AuditMixinNullable

assoc_user_post = Table(
    "ab_user_post",
    Model.metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "user_id",
        Integer,
        ForeignKey("ab_user.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "post_id",
        Integer,
        ForeignKey("ab_post.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # Tracks the last time the user logged in as this post so the picker can
    # pre-select the most recently used post (ADR-5).
    Column("last_used_on", DateTime, nullable=True),
)

assoc_post_role = Table(
    "ab_post_role",
    Model.metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "post_id",
        Integer,
        ForeignKey("ab_post.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "role_id",
        Integer,
        ForeignKey("ab_role.id", ondelete="CASCADE"),
        nullable=False,
    ),
)


class Post(AuditMixinNullable, Model):
    """A named position that a user can log in as, granting a set of roles."""

    __tablename__ = "ab_post"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    label = Column(String(150), nullable=True)
    description = Column(String(512), nullable=True)
    active = Column(Boolean, nullable=False, default=True)

    roles = relationship(
        "Role",
        secondary=assoc_post_role,
        backref=backref("posts", lazy="select"),
        lazy="select",
    )
    users = relationship(
        "User",
        secondary=assoc_user_post,
        backref=backref("posts", lazy="select"),
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"Post<{self.id}: {self.name}>"
