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

test('native chart preview, saved version and follow-up edit render after reconnect', async ({
  page,
}, testInfo) => {
  test.skip(
    !process.env.AI_ARTIFACT_THREAD || !process.env.AI_ARTIFACT_CHART,
    'Requires the dedicated live_artifact_flow.py fixture',
  );
  const chartId = Number(process.env.AI_ARTIFACT_CHART);
  const resource = await page.request.get('/api/v1/chart/' + chartId);
  expect(resource.ok()).toBeTruthy();
  const chart = (await resource.json()).result;
  expect(chart.slice_name).toContain('AI Runtime Evaluation');
  expect(chart.slice_name).toContain('updated');
  expect(JSON.parse(chart.params).all_columns).toEqual(['name', 'color']);
  await page.goto('/ai/' + process.env.AI_ARTIFACT_THREAD);
  const artifacts = page.locator('[data-pane="artifacts"]');
  await expect(
    artifacts.getByRole('heading', { name: 'Artifacts', exact: true }),
  ).toBeVisible();
  await expect(artifacts.locator('table').first()).toBeVisible({
    timeout: 45000,
  });
  await expect(
    page.getByText('Unable to render chart preview.'),
  ).not.toBeVisible();
  await page
    .getByRole('button', { name: 'Inspect Chart preview', exact: true })
    .click();
  await expect(page.locator('[id^="artifact-"]:focus')).toHaveCount(1);
  await page.screenshot({
    path: testInfo.outputPath('native-chart-artifacts.png'),
    fullPage: true,
  });
  await page.reload();
  await expect(artifacts.locator('table').first()).toBeVisible({
    timeout: 45000,
  });
});
