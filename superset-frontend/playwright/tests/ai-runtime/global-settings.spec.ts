/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The ASF licenses this file to You under the Apache License, Version 2.0
 * (the "License"); you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing, software distributed
 * under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
 * CONDITIONS OF ANY KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations under the License.
 */
import { test, expect } from '@playwright/test';

test('a conversation unavailable in the current post opens a clean workspace', async ({
  page,
}) => {
  await page.route('**/api/v1/ai_chat_session/other-post-thread', route =>
    route.fulfill({ status: 404, json: { message: 'Not found' } }),
  );
  await page.goto('/ai/other-post-thread');
  await expect(page).toHaveURL(/\/ai\/$/);
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeVisible();
  await expect(page.getByText('Not found', { exact: true })).toHaveCount(0);
});

test('Chat has no connection configuration and metadata cannot reveal it', async ({
  page,
  request,
}) => {
  await page.goto('/ai/');
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeVisible();
  await page.getByText('Context and tools', { exact: true }).click();
  await expect(
    page.getByRole('combobox', { name: 'Workflows', exact: true }),
  ).toBeVisible();
  for (const name of ['Model profile', 'Connections', 'Connection account'])
    await expect(page.getByRole('combobox', { name, exact: true })).toHaveCount(
      0,
    );
  for (const name of [
    'Manage connections',
    'Connect with OAuth',
    'Link token',
    'Unlink account',
  ])
    await expect(page.getByText(name, { exact: true })).toHaveCount(0);
  const metadata = await (await request.get('/api/v1/ai/runtime/')).json();
  expect(metadata).not.toHaveProperty('connections');
  expect(metadata).not.toHaveProperty('profiles');
  expect(metadata).not.toHaveProperty('can_manage_connections');
});

test('administrator settings own global connections and user-role tool restrictions', async ({
  page,
  request,
}) => {
  await page.goto('/ai/connection/');
  await expect(page.getByLabel('API base URL', { exact: true })).toBeVisible();
  await expect(
    page.getByLabel('MCP server URL', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('combobox', { name: 'Restricted roles', exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByRole('combobox', { name: 'Restricted users', exact: true }),
  ).toBeEnabled();
  const response = await request.get('/api/v1/ai_connection/access-options/');
  expect(response.status()).toBe(200);
  const options = (await response.json()).result;
  expect(options.roles.length).toBeGreaterThan(0);
  expect(options.users.length).toBeGreaterThan(0);
  expect(options.tools).toContain('health_check');
});
