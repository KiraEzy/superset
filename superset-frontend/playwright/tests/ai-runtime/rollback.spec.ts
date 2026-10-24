/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { test, expect } from '@playwright/test';

test('rollback rejects new runtime submissions and preserves accepted records', async ({
  request,
}) => {
  test.skip(
    process.env.AI_EXPECT_RUNTIME_DISABLED !== 'true',
    'Requires the isolated operational rollback phase',
  );
  const csrf = (
    await (await request.get('/api/v1/security/csrf_token/')).json()
  ).result;
  const metadata = await request.get('/api/v1/ai/runtime/');
  expect((await metadata.json()).enabled).toBe(false);
  const turnId = process.env.AI_ROLLBACK_TURN;
  const threadId = process.env.AI_ARTIFACT_THREAD;
  expect(turnId && threadId).toBeTruthy();
  const before = (
    await (await request.get('/api/v1/ai/turns/' + turnId)).json()
  ).result;
  expect(before.status).toBe('completed');
  const response = await request.post(
    '/api/v1/ai/threads/' + threadId + '/turns',
    {
      headers: { 'X-CSRFToken': csrf },
      data: {
        input: 'Must not run during rollback',
        idempotency_key: crypto.randomUUID(),
        connection_ids: [],
        workflow_ids: [],
        context: [],
      },
    },
  );
  expect(response.status()).toBe(503);
  expect((await response.json()).code).toBe('runtime_disabled');
  const after = (await (await request.get('/api/v1/ai/turns/' + turnId)).json())
    .result;
  expect(after).toEqual(before);
});
