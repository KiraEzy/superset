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
"""Best-effort Redis wakeups; all event content and replay remain in the database."""

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

from superset.extensions import celery_app

logger = logging.getLogger(__name__)


def _client() -> Any:
    import redis

    url = str(celery_app.conf.broker_url or "")
    if not url.startswith(("redis://", "rediss://")):
        return None
    return redis.Redis.from_url(url, socket_connect_timeout=0.05, socket_timeout=0.3)


def publish(turn_id: str) -> None:
    """Call only after the database transaction commits; outage is harmless."""
    try:
        client = _client()
        if client is not None:
            client.publish("focal-ai-events:" + turn_id, "changed")
            client.close()
    except Exception:
        logger.debug("AI notification unavailable; database replay remains active")


@contextmanager
def subscription(turn_id: str) -> Iterator[Any]:
    """Wake a subscriber promptly, or fall back to bounded database polling."""
    client = channel = None
    try:
        client = _client()
        if client is not None:
            channel = client.pubsub(ignore_subscribe_messages=True)
            channel.subscribe("focal-ai-events:" + turn_id)
    except Exception:
        channel = None
    try:
        yield channel
    finally:
        if channel is not None:
            channel.close()
        if client is not None:
            client.close()


def wait(channel: Any) -> None:
    """Bound every wait so permission checks and database replay keep running."""
    if channel is not None:
        try:
            channel.get_message(timeout=0.25)
            return
        except Exception:
            logger.debug("AI notification interrupted; using database polling")
    time.sleep(0.25)
