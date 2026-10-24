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
"""Catalogue isolation, revision pinning and image lifecycle contracts."""

import io
from types import SimpleNamespace

import pytest
import test_store
from PIL import Image
from werkzeug.datastructures import FileStorage

ledger = test_store.ledger
test_app = test_store.test_app
payload = test_store.payload


def add_model(ledger, *, vision=False, name="model", status="verified"):
    from superset.ai_runtime import store
    from superset.models.ai_model_catalog import AiModel, AiModelConnection

    conn = AiModelConnection(
        label="Local",
        revision=1,
        config_json=store.dumps(
            {
                "llmProvider": "custom",
                "llmApiBaseUrl": "https://model.example/v1",
                "llmApiKey": "private-key",
                "llmModel": name,
            }
        ),
    )
    ledger.db.session.add(conn)
    ledger.db.session.flush()
    model = AiModel(
        connection_id=conn.id,
        model_name=name,
        revision=1,
        status=status,
        vision=vision,
        position=0,
        is_default=True,
    )
    ledger.db.session.add(model)
    ledger.db.session.commit()
    return conn, model


def image_upload(ledger):
    from superset.ai_runtime import images

    data = io.BytesIO()
    Image.new("RGB", (16, 16), "blue").save(data, format="PNG")
    data.seek(0)
    return images.upload(FileStorage(stream=data, filename="test.png"))


def test_catalogue_public_metadata_and_duplicate_names(ledger):
    from superset.ai_runtime import model_catalog

    add_model(ledger)
    add_model(ledger)
    result = model_catalog.catalogue()
    assert len(result["models"]) == 2
    assert len({m["id"] for m in result["models"]}) == 2
    assert "private-key" not in str(result)
    assert "https://" not in str(result)
    assert all(
        set(m) == {"id", "name", "connection", "vision", "default"}
        for m in result["models"]
    )


def test_model_routing_and_revision_invalidate_continuation(ledger):
    from superset.ai_runtime import model_catalog

    conn, model = add_model(ledger)
    first = ledger.store.submit(
        str(ledger.thread.uuid), {**payload(), "model_id": model.id}
    )
    state = ledger.store.loads(first.state_json)
    assert state["config"]["llmApiKey"] == "private-key"
    assert state["config"]["model_revision"] == 1
    first.status, first.active_key = "completed", None
    state["messages"] = [
        {
            "role": "assistant",
            "content": "answer",
            "reasoning_content": "private opaque data",
        }
    ]
    state["checkpoint"]["continuation"] = {"provider_response_id": "old"}
    first.state_json = ledger.store.dumps(state)
    conn.revision = model.revision = 2
    ledger.db.session.commit()
    second = ledger.store.submit(
        str(ledger.thread.uuid), {**payload("next"), "model_id": model.id}
    )
    next_state = ledger.store.loads(second.state_json)
    assert next_state["checkpoint"]["continuation"] == {}
    assert next_state["messages"] == [{"role": "assistant", "content": "answer"}]
    assert ledger.store.loads(first.state_json)["config"]["model_revision"] == 1
    conn.revision = 3
    ledger.db.session.commit()
    with pytest.raises(ValueError, match="available model"):
        model_catalog.resolve(model.id, {})


def test_publication_rejects_unverified_and_requires_default(ledger):
    from superset.ai_runtime import model_catalog

    conn, model = add_model(ledger, status="discovered")
    with pytest.raises(ValueError, match="Verify"):
        model_catalog.publish([model.id], model.id)
    model.status = "verified"
    ledger.db.session.commit()
    model_catalog.publish([model.id], model.id)
    with pytest.raises(ValueError, match="Select"):
        model_catalog.publish([model.id], "missing")
    with pytest.raises(ValueError, match="Select"):
        model_catalog.publish([], "")


def test_failed_verification_preserves_working_config_and_scrubs_job(
    ledger, monkeypatch
):
    from superset.ai_runtime import model_catalog
    from superset.models.ai_model_catalog import AiModelVerification

    conn, model = add_model(ledger)
    original = conn.config_json
    job_id = model_catalog.queue_connection(
        {
            "id": conn.id,
            "label": "Changed",
            "config": {
                "llmProvider": "custom",
                "llmApiBaseUrl": "https://other.example/v1",
                "llmApiKey": "candidate-secret",
                "llmModel": "other",
            },
        }
    )
    monkeypatch.setattr(
        model_catalog,
        "request_json",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("provider-secret")),
    )
    model_catalog.process_jobs()
    job = ledger.db.session.query(AiModelVerification).get(job_id)
    assert job.status == "failed"
    assert job.candidate_json == "{}"
    assert "provider-secret" not in job.message
    assert conn.config_json == original


def test_masked_key_never_sent_to_changed_destination(ledger):
    from superset.ai_runtime import model_catalog
    from superset.constants import PASSWORD_MASK

    conn, _ = add_model(ledger)
    with pytest.raises(ValueError, match="new key"):
        model_catalog.queue_connection(
            {
                "id": conn.id,
                "label": "Changed",
                "config": {
                    "llmProvider": "custom",
                    "llmApiBaseUrl": "https://other.example/v1",
                    "llmApiKey": PASSWORD_MASK,
                    "llmModel": "other",
                },
            }
        )


def test_successful_discovery_does_not_verify_every_model(ledger, monkeypatch):
    from superset.ai_runtime import model_catalog
    from superset.models.ai_model_catalog import AiModel, AiModelVerification

    conn, model = add_model(ledger)
    job_id = model_catalog.queue_connection(
        {
            "id": conn.id,
            "label": "Local",
            "config": {
                "llmProvider": "custom",
                "llmApiBaseUrl": "https://model.example/v1",
                "llmApiKey": "new-key",
                "llmModel": "model",
            },
        }
    )
    monkeypatch.setattr(
        model_catalog,
        "request_json",
        lambda *a, **k: {"data": [{"id": "model"}, {"id": "embedding"}]},
    )
    monkeypatch.setattr(model_catalog, "probe", lambda *a, **k: None)
    model_catalog.process_jobs()
    assert (
        ledger.db.session.query(AiModelVerification).get(job_id).status == "completed"
    )
    assert conn.revision == 2
    assert model.status == "verified"
    assert model.vision
    other = ledger.db.session.query(AiModel).filter_by(model_name="embedding").one()
    assert other.status == "discovered"
    assert not other.vision
    assert other.position is None


def test_image_binding_and_cross_post_denial(ledger):
    from superset.ai_runtime import images

    _, model = add_model(ledger, vision=True)
    image = image_upload(ledger)
    turn = ledger.store.submit(
        str(ledger.thread.uuid),
        {**payload(), "model_id": model.id, "attachment_ids": [image["id"]]},
    )
    assert images.get(image["id"]).bound
    state = ledger.store.loads(turn.state_json)
    assert state["attachment_ids"] == [image["id"]]
    message = {
        "role": "user",
        "content": [
            {"type": "text", "text": "look"},
            {"type": "image_ref", "image_id": image["id"]},
        ],
    }
    hydrated = images.hydrate([message], state["config"])
    assert hydrated[0]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )
    assert "base64" not in ledger.store.dumps(message)
    ledger.scope["post"] = 12
    with pytest.raises(ledger.store.RuntimeRequestError, match="Image not found"):
        images.get(image["id"])
    with pytest.raises(ValueError, match="unavailable"):
        images.hydrate([message], {**state["config"], "image_post_id": 12})


def test_image_requires_vision_and_rejects_fake_and_animated(ledger):
    from superset.ai_runtime import images

    _, model = add_model(ledger)
    image = image_upload(ledger)
    with pytest.raises(ledger.store.RuntimeRequestError, match="image-verified"):
        ledger.store.submit(
            str(ledger.thread.uuid),
            {**payload(), "model_id": model.id, "attachment_ids": [image["id"]]},
        )
    with pytest.raises(ledger.store.RuntimeRequestError, match="valid JPEG"):
        images.upload(FileStorage(stream=io.BytesIO(b"<svg/>"), filename="fake.png"))
    data = io.BytesIO()
    Image.new("RGB", (2, 2)).save(
        data,
        format="PNG",
        save_all=True,
        append_images=[Image.new("RGB", (2, 2), "blue")],
    )
    data.seek(0)
    with pytest.raises(ledger.store.RuntimeRequestError, match="valid JPEG"):
        images.upload(FileStorage(stream=data, filename="animated.png"))


def test_response_native_image_conversion():
    from superset.ai_runtime.providers import response_input

    result = response_input(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,test"},
                    },
                ],
            }
        ]
    )
    assert result[0]["content"] == [
        {"type": "input_text", "text": "look"},
        {"type": "input_image", "image_url": "data:image/png;base64,test"},
    ]


def test_admin_catalogue_endpoints_reject_nonadmin_even_with_route_access(
    ledger, monkeypatch
):
    import inspect

    from superset.views.ai import config_api

    monkeypatch.setattr(
        config_api, "security_manager", SimpleNamespace(is_admin=lambda: False)
    )
    api = config_api.AIConnectionRestApi.__new__(config_api.AIConnectionRestApi)
    for name, args in (
        ("catalog", ()),
        ("verify_connection", ()),
        ("verify_model", ("model",)),
        ("verification", ("job",)),
        ("publish_models", ()),
        ("delete_connection", ("conn",)),
        ("reasoning_visibility", ("conn",)),
    ):
        response, status = inspect.unwrap(
            getattr(config_api.AIConnectionRestApi, name)
        )(api, *args)
        assert status == 403


def test_reference_limit_counts_retained_images_and_cleanup_preserves_bound(ledger):
    from datetime import datetime, timedelta

    from superset.ai_runtime import images
    from superset.models.ai_model_catalog import AiChatImage

    messages = [
        {
            "role": "user",
            "content": [{"type": "image_ref", "image_id": str(i)} for i in range(4)],
        }
    ]
    with pytest.raises(ledger.store.RuntimeRequestError, match="image limit"):
        images.references(["fifth"], messages, vision=True)
    first = image_upload(ledger)
    second = image_upload(ledger)
    images.get(first["id"]).created_on = datetime.utcnow() - timedelta(days=2)
    saved = images.get(second["id"])
    saved.created_on = datetime.utcnow() - timedelta(days=2)
    saved.bound = True
    ledger.db.session.commit()
    assert images.cleanup() == 1
    assert ledger.db.session.query(AiChatImage).get(second["id"]) is not None


def test_probe_does_not_accept_a_second_tool_call_as_final_text(monkeypatch):
    import re

    from superset.ai_runtime import model_catalog

    marker = ""

    def response(config, path, body):
        nonlocal marker
        marker = marker or re.search(
            r"verified_[a-f0-9]+", body["messages"][0]["content"]
        ).group(0)
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "synthetic",
                                "type": "function",
                                "function": {
                                    "name": "verification_echo",
                                    "arguments": model_catalog.json.dumps(
                                        {"marker": marker}
                                    ),
                                },
                            }
                        ],
                    }
                }
            ]
        }

    monkeypatch.setattr(model_catalog, "request_json", response)
    with pytest.raises(ValueError, match="round-trip"):
        model_catalog.probe({"llmModel": "model"})


def test_fork_retry_edit_preserve_private_image_references(ledger):
    from superset.ai_runtime import images

    _, model = add_model(ledger, vision=True)
    image = image_upload(ledger)
    source = ledger.store.submit(
        str(ledger.thread.uuid),
        {**payload(), "model_id": model.id, "attachment_ids": [image["id"]]},
    )
    source.status, source.active_key = "completed", None
    state = ledger.store.loads(source.state_json)
    state["messages"] = [
        {"role": "user", "content": [{"type": "image_ref", "image_id": image["id"]}]}
    ]
    source.state_json = ledger.store.dumps(state)
    ledger.db.session.commit()
    copied = ledger.store.fork(ledger.thread, source.id, include_turn=True)
    assert ledger.store.history(copied)[0]["content"][0]["image_id"] == image["id"]
    for mode in ("retry", "edit"):
        branch = ledger.store.branch_reply(
            ledger.thread, source.id, mode, edited_input="Revised", model_id=model.id
        )
        turn = (
            ledger.db.session.query(ledger.Turn).filter_by(session_id=branch.id).one()
        )
        assert ledger.store.loads(turn.state_json)["attachment_ids"] == [image["id"]]
        assert ledger.store.loads(turn.state_json)["config"]["model_id"] == model.id
    assert images.get(image["id"]).bound


def test_invalid_retry_model_does_not_create_an_empty_branch(ledger):
    from superset.models.ai_chat import AiChatSession

    _, model = add_model(ledger)
    source = ledger.store.submit(
        str(ledger.thread.uuid), {**payload(), "model_id": model.id}
    )
    source.status, source.active_key = "completed", None
    ledger.db.session.commit()
    before = ledger.db.session.query(AiChatSession).count()
    with pytest.raises(ValueError, match="available model"):
        ledger.store.branch_reply(
            ledger.thread, source.id, "retry", model_id="unpublished"
        )
    assert ledger.db.session.query(AiChatSession).count() == before


def test_reasoning_preference_pins_new_turns_without_invalidating_models(ledger):
    from superset.ai_runtime import model_catalog

    conn, model = add_model(ledger)
    first = ledger.store.submit(
        str(ledger.thread.uuid), {**payload(), "model_id": model.id}
    )
    first.status, first.active_key = "completed", None
    ledger.db.session.commit()
    model_catalog.save_reasoning_visibility(conn.id, True)
    second = ledger.store.submit(
        str(ledger.thread.uuid), {**payload("second"), "model_id": model.id}
    )
    assert ledger.store.loads(second.state_json)["config"]["showModelReasoning"] is True
    assert (
        ledger.store.loads(first.state_json)["config"].get("showModelReasoning", False)
        is False
    )
    assert conn.revision == model.revision == 1
    assert ledger.store.loads(conn.config_json)["llmApiKey"] == "private-key"
    assert "showModelReasoning" not in str(model_catalog.catalogue())
    with pytest.raises(ValueError, match="boolean"):
        model_catalog.save_reasoning_visibility(conn.id, "true")
    config = ledger.store.loads(conn.config_json)
    config["llmProvider"] = "openai"
    conn.config_json = ledger.store.dumps(config)
    ledger.db.session.commit()
    with pytest.raises(ValueError, match="self-hosted"):
        model_catalog.save_reasoning_visibility(conn.id, True)


def test_reasoning_display_does_not_race_pending_verification(ledger):
    from superset.ai_runtime import model_catalog
    from superset.models.ai_model_catalog import AiModelVerification

    conn, model = add_model(ledger)
    job = AiModelVerification(
        connection_id=conn.id,
        expected_revision=1,
        candidate_json="{}",
        kind="connection",
        status="queued",
    )
    ledger.db.session.add(job)
    ledger.db.session.commit()
    with pytest.raises(ValueError, match="verification"):
        model_catalog.save_reasoning_visibility(conn.id, True)
    assert (
        ledger.store.loads(conn.config_json).get("showModelReasoning", False) is False
    )
