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
"""Dedicated AI worker and dispatcher; leaves existing worker/server config intact."""

from celery import Celery
from celery.signals import worker_process_init

from superset.app import create_app
from superset.extensions import celery_app, db

flask_app = create_app()
app = Celery("focal_ai", broker=celery_app.conf.broker_url)
app.conf.update(
    task_default_queue="ai",
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "ai-dispatch": {"task": "ai_runtime.dispatch", "schedule": 10.0},
        "ai-recover": {"task": "ai_runtime.recover", "schedule": 20.0},
    },
)


@worker_process_init.connect
def reset_ai_pool(**kwargs: object) -> None:
    """Discard inherited connections before a forked worker uses the ledger."""
    with flask_app.app_context():
        db.engine.dispose()


@app.task(name="ai_runtime.execute")
def execute(turn_id: str) -> None:
    """Run one claimed turn in its own Flask context."""
    from superset.ai_runtime.runner import execute_turn

    with flask_app.app_context():
        execute_turn(turn_id)


@app.task(name="ai_runtime.dispatch", soft_time_limit=300, time_limit=330)
def dispatch() -> int:
    """Drain accepted inputs after transient broker/publisher outages."""
    from superset.ai_runtime.runner import dispatch_pending

    with flask_app.app_context():
        from superset.ai_runtime.images import cleanup
        from superset.ai_runtime.model_catalog import process_jobs

        dispatched = dispatch_pending()
        cleanup()
        process_jobs()
        return dispatched


@app.task(name="ai_runtime.recover")
def recover() -> int:
    """Recover expired workers without repeating uncertain writes."""
    from superset.ai_runtime.runner import recover_stale

    with flask_app.app_context():
        return recover_stale()
