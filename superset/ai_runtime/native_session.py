# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.
"""SDK Session protocol over SQLAlchemy 1.4, without a second transcript."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from functools import lru_cache
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import declarative_base

from superset.utils import json

from .contracts import AiRuntimeError

Base: Any = declarative_base()


@lru_cache(maxsize=1)
def application_models() -> tuple[Any, Any]:
    """Initialize the application's encrypted SDK models exactly once."""
    from superset.models.ai_runtime import encrypted_text

    return session_models(encrypted_text())


@lru_cache(maxsize=1)
def session_models(payload_type: Any) -> tuple[Any, Any]:
    """Create isolated tables using the application's encrypted payload type."""

    # A separate metadata object keeps SDK storage out of external MCP models.
    class SessionRow(Base):
        __tablename__ = "ai_sdk_session"
        id = Column(String(36), primary_key=True)
        owner_id = Column(Integer, nullable=False)
        post_id = Column(Integer, nullable=False)
        revision = Column(Integer, nullable=False, default=0)
        binding = Column(String(64), nullable=False)

    class ItemRow(Base):
        __tablename__ = "ai_sdk_item"
        __table_args__ = (UniqueConstraint("session_id", "position"),)
        id = Column(String(36), primary_key=True)
        session_id = Column(
            String(36), ForeignKey("ai_sdk_session.id"), nullable=False, index=True
        )
        position = Column(Integer, nullable=False)
        payload = Column(payload_type, nullable=False)

    class SummaryRow(Base):
        __tablename__ = "ai_sdk_summary"
        session_id = Column(
            String(36),
            ForeignKey("ai_sdk_session.id", ondelete="CASCADE"),
            primary_key=True,
        )
        owner_id = Column(Integer, nullable=False)
        post_id = Column(Integer, nullable=False)
        binding = Column(String(64), nullable=False)
        boundary = Column(Integer, nullable=False)
        fingerprint = Column(String(64), nullable=False)
        policy_version = Column(Integer, nullable=False)
        payload = Column(payload_type, nullable=False)
        created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    SessionRow.summary_model = SummaryRow
    return SessionRow, ItemRow


class FocalSession:
    """One scoped SDK item stream; callers provide a live lease check."""

    session_settings = None

    def __init__(
        self,
        session_id: str,
        *,
        database: Any,
        models: tuple[Any, Any],
        owner_id: int,
        post_id: int,
        binding: str,
        turn_id: str,
        guard: Callable[[], Any],
        offset: int = 0,
        allow_rebind: bool = False,
    ) -> None:
        self.session_id = session_id
        self.db, self.rows = database, models
        self.owner_id, self.post_id = owner_id, post_id
        self.binding, self.turn_id, self.guard = binding, turn_id, guard
        self.offset = offset
        self.allow_rebind = allow_rebind
        self.revision: int | None = None

    async def truncate(self, length: int) -> None:
        """Rewind an unexecuted interrupted turn under its exclusive lease."""
        row = self._row()
        session, item = self.rows
        revision = self.revision if self.revision is not None else row.revision
        if length < 0:
            raise ValueError("Invalid session boundary")
        self.db.query(session.summary_model).filter(
            session.summary_model.session_id == self.session_id,
            session.summary_model.boundary > length,
        ).delete(synchronize_session=False)
        self.db.query(item).filter(
            item.session_id == self.session_id, item.position >= length
        ).delete(synchronize_session=False)
        if (
            self.db.query(session)
            .filter_by(id=row.id, revision=revision)
            .update({"revision": revision + 1}, synchronize_session=False)
            != 1
        ):
            self.db.rollback()
            raise AiRuntimeError(
                "Session changed concurrently", code="session_conflict"
            )
        self.db.commit()
        self.db.expire_all()
        self.revision = revision + 1
        self.offset = 0

    def _row(self) -> Any:
        self.guard()
        model, _ = self.rows
        row = self.db.query(model).filter_by(id=self.session_id).one_or_none()
        if row is None:
            row = model(
                id=self.session_id,
                owner_id=self.owner_id,
                post_id=self.post_id,
                binding=self.binding,
                revision=0,
            )
            self.db.add(row)
            self.db.flush()
        if (row.owner_id, row.post_id) != (
            self.owner_id,
            self.post_id,
        ):
            raise AiRuntimeError(
                "Session scope or model changed; start a new chat", code="session_scope"
            )
        if row.binding != self.binding:
            if not self.allow_rebind:
                raise AiRuntimeError(
                    "Model changed during an active run", code="session_scope"
                )
            row.binding = self.binding
            row.revision += 1
            self.db.flush()
        self.allow_rebind = False
        return row

    async def get_items(self, limit: int | None = None) -> list[Any]:
        """Return original SDK items; model filtering cannot mutate stored history."""
        row = self._row()
        self.revision = row.revision
        _, item = self.rows
        query = self.db.query(item).filter_by(session_id=self.session_id)
        if limit is not None:
            if limit < 0:
                raise ValueError("Session limit cannot be negative")
            rows = list(
                reversed(query.order_by(item.position.desc()).limit(limit).all())
            )
        else:
            rows = query.order_by(item.position).all()
        return [json.loads(row.payload) for row in rows]

    async def add_items(self, items: list[Any]) -> None:
        """Append under revision CAS; repeated delivery must contain identical items."""
        row = self._row()
        session, item = self.rows
        revision = self.revision if self.revision is not None else row.revision
        count = self.db.query(item).filter_by(session_id=self.session_id).count()
        for value in items:
            identifier = str(uuid5(NAMESPACE_URL, f"{self.turn_id}:{self.offset}"))
            self.offset += 1
            payload = json.dumps(value, sort_keys=True)
            previous = self.db.query(item).filter_by(id=identifier).one_or_none()
            if previous is not None:
                if (
                    previous.payload != payload
                    or previous.session_id != self.session_id
                ):
                    raise AiRuntimeError(
                        "Session replay differs", code="session_conflict"
                    )
                continue
            self.db.add(
                item(
                    id=identifier,
                    session_id=self.session_id,
                    position=count,
                    payload=payload,
                )
            )
            count += 1
        updated = (
            self.db.query(session)
            .filter_by(id=self.session_id, revision=revision)
            .update({"revision": revision + 1}, synchronize_session=False)
        )
        if updated != 1:
            self.db.rollback()
            raise AiRuntimeError(
                "Session changed concurrently", code="session_conflict"
            )
        self.db.commit()
        self.db.expire_all()
        self.revision = revision + 1

    async def pop_item(self) -> Any:
        """Remove the last item under the same scoped mutation guard."""
        row = self._row()
        session, item = self.rows
        revision = self.revision if self.revision is not None else row.revision
        last = (
            self.db.query(item)
            .filter_by(session_id=self.session_id)
            .order_by(item.position.desc())
            .first()
        )
        if last is None:
            return None
        value = json.loads(last.payload)
        self.db.delete(last)
        if (
            self.db.query(session)
            .filter_by(id=row.id, revision=revision)
            .update({"revision": revision + 1}, synchronize_session=False)
            != 1
        ):
            self.db.rollback()
            raise AiRuntimeError(
                "Session changed concurrently", code="session_conflict"
            )
        self.db.commit()
        self.db.expire_all()
        self.revision = revision + 1
        return value

    async def clear_session(self) -> None:
        """Clear only this authorized SDK session, never connections or BI data."""
        row = self._row()
        session, item = self.rows
        revision = self.revision if self.revision is not None else row.revision
        self.db.query(session.summary_model).filter_by(
            session_id=self.session_id
        ).delete()
        self.db.query(item).filter_by(session_id=self.session_id).delete()
        if (
            self.db.query(session)
            .filter_by(id=row.id, revision=revision)
            .update({"revision": revision + 1}, synchronize_session=False)
            != 1
        ):
            self.db.rollback()
            raise AiRuntimeError(
                "Session changed concurrently", code="session_conflict"
            )
        self.db.commit()
        self.db.expire_all()
        self.revision = revision + 1

    def summary_snapshot(self) -> tuple[int, dict[str, Any] | None]:
        """Read a scoped checkpoint and revision without altering SDK item offsets."""
        self.db.expire_all()
        row = self._row()
        summary = (
            self.db.query(self.rows[0].summary_model)
            .filter_by(
                session_id=self.session_id,
                owner_id=self.owner_id,
                post_id=self.post_id,
                binding=self.binding,
            )
            .one_or_none()
        )
        value = (
            None
            if summary is None
            else {
                "boundary": summary.boundary,
                "fingerprint": summary.fingerprint,
                "policy_version": summary.policy_version,
                **json.loads(summary.payload),
            }
        )
        revision = row.revision
        self.revision = revision
        # Release the read transaction before the potentially slow model call.
        self.db.commit()
        return revision, value

    def save_summary(
        self, revision: int, value: dict[str, Any], source: list[Any] | None = None
    ) -> bool:
        """Publish a summary only while its lease, scope and source revision hold."""
        self.db.expire_all()
        row = self._row()
        session, item = self.rows
        if source is not None:
            stored = [
                json.loads(record.payload)
                for record in self.db.query(item)
                .filter_by(session_id=self.session_id)
                .order_by(item.position)
            ]
            if stored != source[: len(stored)]:
                self.db.rollback()
                return False
        updated = (
            self.db.query(session)
            .filter_by(
                id=row.id,
                revision=revision,
                binding=self.binding,
            )
            .update({"revision": revision + 1}, synchronize_session=False)
        )
        if updated != 1:
            self.db.rollback()
            return False
        model = session.summary_model
        self.db.query(model).filter_by(session_id=self.session_id).delete()
        self.db.add(
            model(
                session_id=self.session_id,
                owner_id=self.owner_id,
                post_id=self.post_id,
                binding=self.binding,
                boundary=value["boundary"],
                fingerprint=value["fingerprint"],
                policy_version=value["policy_version"],
                payload=json.dumps(
                    {"summary": value["summary"], "request": value.get("request")}
                ),
            )
        )
        self.db.commit()
        self.db.expire_all()
        self.revision = revision + 1
        return True
