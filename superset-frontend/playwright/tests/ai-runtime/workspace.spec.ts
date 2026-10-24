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
import type { Turn } from '../../../src/features/ai/runtime';

test('real task survives page refresh and keeps its conversation URL', async ({
  page,
}, testInfo) => {
  await page.addInitScript(() =>
    Object.defineProperty(globalThis.crypto, 'randomUUID', {
      value: undefined,
      configurable: true,
    }),
  );
  await page.goto('/ai/');
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeVisible();
  const accepted = page.waitForResponse(
    response =>
      /\/threads\/[^/]+\/turns$/.test(response.url()) &&
      response.status() === 202,
  );
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Check the Focal BI connection health. Report only its status.');
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .press('Control+Enter');
  const turn = (await (await accepted).json()).result;
  await expect(page).toHaveURL(new RegExp('/ai/' + turn.thread_id));
  await page.reload();
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeVisible();
  await expect
    .poll(
      async () => {
        const response = await page.request.get('/api/v1/ai/turns/' + turn.id);
        return (await response.json()).result.status;
      },
      { timeout: 150000 },
    )
    .toBe('completed');
  await page.reload();
  await expect(
    page.getByRole('button', { name: 'Fork chat', exact: true }).last(),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath('desktop.png'),
    fullPage: true,
  });
});

test('approval, steering, clarification and mobile artifact inspection', async ({
  page,
}, testInfo) => {
  let turn: Turn = {
    id: 'fixture-turn',
    thread_id: 'fixture-thread',
    status: 'waiting_approval',
    content: 'A chart edit is ready for review.',
    items: [],
    artifacts: [],
    pending_requests: [
      {
        id: 'approval',
        kind: 'approval',
        message: 'Review this chart edit',
        tool: 'fixture__update_chart',
        arguments: { chart_id: 999, title: 'Test chart' },
      },
    ],
    last_sequence: 1,
  };
  await page.route('**/api/v1/ai_chat_session/fixture-thread', route =>
    route.fulfill({
      json: {
        result: {
          id: 999,
          uuid: 'fixture-thread',
          title: 'Runtime interaction checks',
          messages: [],
          active_turn: { id: turn.id, status: turn.status },
        },
      },
    }),
  );
  await page.route('**/api/v1/ai/turns/fixture-turn**', async route => {
    const request = route.request();
    if (request.url().includes('/events')) {
      await route.fulfill({
        contentType: 'text/event-stream',
        body: ': fixture\n\n',
      });
      return;
    }
    if (request.method() === 'POST') {
      const payload = request.postDataJSON();
      if (request.url().endsWith('/cancel'))
        turn = {
          ...turn,
          status: 'cancelled',
          pending_requests: [],
          last_sequence: 6,
        };
      else if (payload.request_id === 'approval')
        turn = {
          ...turn,
          status: 'running',
          pending_requests: [],
          last_sequence: 2,
        };
      else if (payload.input)
        turn = {
          ...turn,
          status: 'waiting_input',
          last_sequence: 3,
          pending_requests: [
            {
              id: 'question',
              kind: 'clarification',
              message: 'Which metric?',
              tool: '',
              arguments: { chart_id: 999, title: '' },
            },
          ],
        };
      else
        turn = {
          ...turn,
          status: 'completed',
          pending_requests: [],
          last_sequence: 4,
          artifacts: [
            {
              id: 'table-1',
              type: 'table',
              title: 'Verified results',
              version: 1,
              saved: false,
              payload: { rows: [{ period: 'January', revenue: 42 }] },
            },
          ],
        };
    }
    await route.fulfill({ json: { result: turn } });
  });
  await page.goto('/ai/fixture-thread');
  await expect(page.getByText('Review this chart edit')).toBeVisible();
  await expect(page.getByText(/"chart_id": 999/)).toBeVisible();
  await page.getByRole('button', { name: 'Approve', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('button', { name: 'Stop', exact: true }),
  ).toBeVisible();
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Use revenue');
  await page.getByRole('button', { name: 'Send guidance' }).click();
  await page.getByRole('textbox', { name: 'Which metric?' }).fill('Revenue');
  await page.getByRole('button', { name: 'Submit answer' }).click();
  await expect(
    page.getByRole('table', { name: 'Verified results' }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Artifacts', exact: true }).click();
  await expect(
    page.getByRole('table', { name: 'Verified results' }),
  ).toBeVisible();
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).not.toBeVisible();
  // Superset's existing global menu has its own responsive behavior; verify
  // that the new Chat pane itself stays within the mobile viewport.
  expect(
    await page
      .locator('[data-section]')
      .evaluate(
        element => element.getBoundingClientRect().right <= window.innerWidth,
      ),
  ).toBeTruthy();
  await page.screenshot({
    path: testInfo.outputPath('mobile-artifacts.png'),
    fullPage: true,
  });
  await page.getByRole('button', { name: 'Chat', exact: true }).click();
  await expect(
    page.getByRole('textbox', { name: 'Message', exact: true }),
  ).toBeVisible();
  turn = { ...turn, status: 'running', pending_requests: [], last_sequence: 5 };
  await page.reload();
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Stop', exact: true }),
  ).not.toBeVisible();
  expect(turn.status).toBe('cancelled');
});
