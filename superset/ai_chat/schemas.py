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
from marshmallow import fields, Schema, validate

openapi_spec_methods_override = {
    "get": {"get": {"summary": "Get an AI chat session"}},
    "get_list": {
        "get": {
            "summary": "Get a list of AI chat sessions",
            "description": "Gets a list of AI chat sessions for the current user.",
        }
    },
    "post": {"post": {"summary": "Create an AI chat session"}},
    "put": {"put": {"summary": "Update an AI chat session"}},
    "delete": {"delete": {"summary": "Delete an AI chat session"}},
    "info": {"get": {"summary": "Get metadata information about this API resource"}},
}


class AiChatMessageSchema(Schema):
    id = fields.Integer()
    role = fields.String(required=True, validate=validate.OneOf(["user", "assistant"]))
    content = fields.String(required=True)
    extra = fields.Dict(allow_none=True)
    created_on = fields.DateTime()


class AiChatSessionPostSchema(Schema):
    title = fields.String(validate=validate.Length(max=256), load_default="New chat")


class AiChatSessionPutSchema(Schema):
    title = fields.String(required=True, validate=validate.Length(1, 256))


class AiChatMessagePostSchema(Schema):
    role = fields.String(required=True, validate=validate.OneOf(["user", "assistant"]))
    content = fields.String(required=True)
    extra = fields.Dict(allow_none=True)


class AiChatSessionResponseSchema(Schema):
    id = fields.Integer()
    uuid = fields.String()
    title = fields.String()
    changed_on = fields.DateTime()
    created_on = fields.DateTime()
    messages = fields.List(fields.Nested(AiChatMessageSchema))


class AiChatSessionSummarySchema(Schema):
    id = fields.Integer()
    uuid = fields.String()
    title = fields.String()
    changed_on = fields.DateTime()
    created_on = fields.DateTime()
