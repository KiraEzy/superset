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
"""Private image uploads and inference-time provider hydration."""

from __future__ import annotations

import base64
import io
import warnings
from datetime import datetime, timedelta
from typing import Any

from flask import current_app
from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from superset.ai_runtime import store
from superset.extensions import db
from superset.models.ai_model_catalog import AiChatImage


def limits() -> dict[str, int]:
    """Return shared client/server attachment limits."""
    return {
        "count": int(current_app.config.get("AI_IMAGE_MAX_COUNT", 4)),
        "bytes": int(current_app.config.get("AI_IMAGE_MAX_BYTES", 5 * 1024 * 1024)),
        "pixels": int(current_app.config.get("AI_IMAGE_MAX_PIXELS", 20_000_000)),
    }


def upload(file: FileStorage) -> dict[str, str]:
    """Decode an allowed static format, re-encode without metadata, then encrypt."""
    user_id, post_id = store.current_scope()
    bounds = limits()
    raw = file.stream.read(bounds["bytes"] + 1)
    if not raw or len(raw) > bounds["bytes"]:
        raise store.RuntimeRequestError("Image exceeds the upload size limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if (
                    image.format not in {"JPEG", "PNG", "WEBP"}
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise ValueError("Use JPEG, PNG or static WebP images")
                if image.width * image.height > bounds["pixels"]:
                    raise ValueError("Image exceeds the pixel limit")
                image.load()
                output = io.BytesIO()
                image.convert("RGBA" if "A" in image.getbands() else "RGB").save(
                    output, format="PNG"
                )
                if len(output.getvalue()) > bounds["bytes"]:
                    raise ValueError("Decoded image exceeds the upload size limit")
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as ex:
        raise store.RuntimeRequestError(
            "Use a valid JPEG, PNG or static WebP within the image limits"
        ) from ex
    # Cap abandoned drafts per user/post and expire only unbound drafts.
    cleanup()
    if (
        db.session.query(AiChatImage)
        .filter_by(user_id=user_id, post_id=post_id, bound=False)
        .count()
        >= 20
    ):
        raise store.RuntimeRequestError(
            "Remove unused image uploads before adding more"
        )
    row = AiChatImage(
        user_id=user_id,
        post_id=post_id,
        filename=(secure_filename(file.filename or "image")[:120] or "image") + ".png",
        mime="image/png",
        data=base64.b64encode(output.getvalue()).decode(),
    )
    db.session.add(row)
    db.session.commit()
    return descriptor(row)


def descriptor(row: AiChatImage) -> dict[str, str]:
    """Expose only stable private image references."""
    return {"id": row.id, "name": row.filename, "url": f"/api/v1/ai/images/{row.id}"}


def get(identifier: str) -> AiChatImage:
    """Authorize every preview/removal against the active actor and post."""
    user_id, post_id = store.current_scope()
    row = (
        db.session.query(AiChatImage)
        .filter_by(id=identifier, user_id=user_id, post_id=post_id)
        .with_for_update()
        .one_or_none()
    )
    if not row:
        raise store.RuntimeRequestError("Image not found", 404)
    return row


def references(
    ids: Any, messages: list[dict[str, Any]], *, vision: bool
) -> list[dict[str, str]]:
    """Validate all retained references; never silently discard older images."""
    if (
        not isinstance(ids, list)
        or any(not isinstance(i, str) for i in ids)
        or len(ids) != len(set(ids))
    ):
        raise store.RuntimeRequestError("Invalid image selection")
    retained = {
        part["image_id"]
        for m in messages
        for part in (m["content"] if isinstance(m.get("content"), list) else [])
        if part.get("type") == "image_ref"
    }
    if len(retained | set(ids)) > limits()["count"]:
        raise store.RuntimeRequestError(
            "Conversation image limit reached; start a focused new chat"
        )
    if (retained or ids) and not vision:
        raise store.RuntimeRequestError(
            "Choose an image-verified model for this conversation"
        )
    for identifier in retained | set(ids):
        get(identifier)
    return [descriptor(get(i)) for i in ids]


def hydrate(
    messages: list[dict[str, Any]], config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Build transient native image content; never persist or emit image bytes."""
    result = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            result.append(message)
            continue
        parts = []
        for part in content:
            if part.get("type") != "image_ref":
                parts.append(dict(part))
                continue
            row = (
                db.session.query(AiChatImage)
                .filter_by(
                    id=part["image_id"],
                    user_id=config.get("image_user_id"),
                    post_id=config.get("image_post_id"),
                    bound=True,
                )
                .one_or_none()
            )
            if not row:
                raise ValueError("Conversation image is unavailable")
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": "data:" + row.mime + ";base64," + row.data},
                }
            )
        result.append({**message, "content": parts})
    return result


def cleanup() -> int:
    """Remove abandoned uploads only; bound images survive forks and deletion."""
    count = (
        db.session.query(AiChatImage)
        .filter(
            AiChatImage.bound.is_(False),
            AiChatImage.created_on < datetime.utcnow() - timedelta(hours=24),
        )
        .delete()
    )
    db.session.commit()
    return count
