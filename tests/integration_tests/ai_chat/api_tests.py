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
"""Integration tests for AI chat session API."""

from superset import db
from superset.models.ai_chat import AiChatMessage, AiChatSession
from tests.integration_tests.base_tests import SupersetTestCase
from tests.integration_tests.constants import ADMIN_USERNAME, GAMMA_USERNAME


class TestAiChatSessionApi(SupersetTestCase):
    def create_session(self, username: str = ADMIN_USERNAME, title: str = "Test chat"):
        with self.create_app().app_context():
            user = self.get_user(username)
            session = AiChatSession(title=title, created_by=user, changed_by=user)
            db.session.add(session)
            db.session.commit()
            return session

    def cleanup_session(self, session_id: int) -> None:
        with self.create_app().app_context():
            session = db.session.query(AiChatSession).get(session_id)
            if session:
                db.session.delete(session)
                db.session.commit()

    def test_create_list_get_append_delete(self):
        self.login(ADMIN_USERNAME)
        uri = "api/v1/ai_chat_session/"

        create_response = self.post_assert_metric(
            uri,
            {"title": "My chat"},
            "post",
        )
        assert create_response.status_code == 201
        created = create_response.json["result"]
        session_uuid = created["uuid"]
        session_id = created["id"]

        try:
            list_response = self.get_assert_metric(uri, "get_list")
            assert list_response.status_code == 200
            uuids = [item["uuid"] for item in list_response.json["result"]]
            assert session_uuid in uuids

            get_response = self.get_assert_metric(
                f"{uri}{session_uuid}",
                "get",
            )
            assert get_response.status_code == 200
            assert get_response.json["result"]["messages"] == []

            append_response = self.post_assert_metric(
                f"{uri}{session_uuid}/message/",
                {"role": "user", "content": "Hello"},
                "append_message",
            )
            assert append_response.status_code == 201
            assert append_response.json["result"]["message"]["content"] == "Hello"

            get_response = self.get_assert_metric(
                f"{uri}{session_uuid}",
                "get",
            )
            assert len(get_response.json["result"]["messages"]) == 1

            delete_response = self.delete_assert_metric(
                f"{uri}{session_uuid}",
                "delete",
            )
            assert delete_response.status_code == 200
            session_id = None

            missing_response = self.client.get(f"{uri}{session_uuid}")
            assert missing_response.status_code == 404
        finally:
            if session_id is not None:
                self.cleanup_session(session_id)

    def test_user_cannot_access_other_users_session(self):
        session = self.create_session(username=ADMIN_USERNAME, title="Admin chat")
        try:
            self.login(GAMMA_USERNAME)
            response = self.client.get(f"api/v1/ai_chat_session/{session.uuid}")
            assert response.status_code == 404
        finally:
            self.cleanup_session(session.id)

    def test_delete_cascades_messages(self):
        self.login(ADMIN_USERNAME)
        uri = "api/v1/ai_chat_session/"

        create_response = self.post_assert_metric(uri, {"title": "Cascade chat"}, "post")
        session_uuid = create_response.json["result"]["uuid"]
        session_id = create_response.json["result"]["id"]

        self.post_assert_metric(
            f"{uri}{session_uuid}/message/",
            {"role": "user", "content": "Hi"},
            "append_message",
        )

        self.delete_assert_metric(f"{uri}{session_uuid}", "delete")

        with self.create_app().app_context():
            assert (
                db.session.query(AiChatMessage).filter_by(session_id=session_id).count()
                == 0
            )
            assert db.session.query(AiChatSession).get(session_id) is None
