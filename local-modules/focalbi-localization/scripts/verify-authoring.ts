/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership. The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License. You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync, writeFileSync } from "node:fs";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(
  resolve(root, "../../superset-frontend/package.json"),
);
const { chromium } = require("playwright");
const fixture = JSON.parse(
  readFileSync(
    resolve(root, ".runtime/localization-test-resources.json"),
    "utf8",
  ),
);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({
  viewport: { width: 1600, height: 1100 },
});
await context.addCookies([
  JSON.parse(readFileSync(resolve(root, ".runtime/admin-cookie.json"), "utf8")),
]);
const page = await context.newPage();
page.setDefaultTimeout(60000);
const errors: string[] = [];
let queries = 0;
page.on("pageerror", (error: Error) => errors.push(error.message));
page.on("request", (request: { url(): string }) => {
  if (request.url().includes("/api/v1/chart/data")) queries++;
});
async function language(option: string) {
  await page
    .locator('[data-test="focalbi-localization-toolbar"] .ant-select-selector')
    .click();
  await page
    .locator(".ant-select-dropdown:visible .ant-select-item-option-content")
    .getByText(option, { exact: true })
    .click();
}
try {
  await page.goto(
    `http://localhost:8088/explore/?slice_id=${fixture.charts[0].id}&content_locale=zh-Hant`,
    { waitUntil: "domcontentloaded" },
  );
  await page
    .getByRole("button", { name: "Translations", exact: true })
    .waitFor();
  await page.waitForFunction(
    () =>
      (
        document.querySelector(
          'input[aria-label="Chart title"]',
        ) as HTMLInputElement
      )?.value === "繁體 Synthetic pie",
  );
  console.log("Explore title localized");
  const nativeTitle = page.getByRole("textbox", {
    name: "Chart title",
    exact: true,
  });
  await nativeTitle.click();
  assert.equal(
    await nativeTitle.inputValue(),
    "Synthetic pie",
    "Editing uses native text",
  );
  await page.getByText("Content language", { exact: true }).click();
  assert.equal(
    await nativeTitle.inputValue(),
    "繁體 Synthetic pie",
    "Idle preview restores translation",
  );
  await page.getByRole("button", { name: "Translations", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Chart title zh-Hant", exact: true })
    .waitFor();
  assert.equal(
    await page
      .getByRole("textbox", { name: "Chart title zh-Hant", exact: true })
      .inputValue(),
    "繁體 Synthetic pie",
  );
  await page.getByRole("button", { name: "Close", exact: true }).last().click();
  await page.waitForTimeout(2500);
  const beforeExplore = queries;
  await language("English");
  await page.waitForFunction(
    () =>
      (
        document.querySelector(
          'input[aria-label="Chart title"]',
        ) as HTMLInputElement
      )?.value === "Synthetic pie",
  );
  await page.waitForTimeout(1500);
  assert.equal(queries, beforeExplore, "Explore locale does not re-query");
  await page.route(
    "**/content-localization/catalog/bundle/**",
    (route: { fulfill(data: object): Promise<void> }) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: '{"message":"test failure"}',
      }),
  );
  await language("简体中文");
  await page
    .getByText("Translations unavailable. Original content is displayed.", {
      exact: true,
    })
    .waitFor();
  assert.equal(
    await page
      .getByRole("textbox", { name: "Chart title", exact: true })
      .inputValue(),
    "Synthetic pie",
  );
  assert.equal(queries, beforeExplore, "Catalog failure does not re-query");
  await page.unroute("**/content-localization/catalog/bundle/**");
  await page.goto("http://localhost:8088/tablemodelview/list/", {
    waitUntil: "domcontentloaded",
  });
  const dataset = (
    await (
      await page.request.get(
        `http://localhost:8088/api/v1/dataset/${fixture.dataset.id}`,
      )
    ).json()
  ).result;
  const row = page.getByRole("row").filter({ hasText: dataset.table_name });
  await row.waitFor();
  await row.locator('span[role="button"]').first().click();
  await page
    .getByRole("button", { name: "Translations", exact: true })
    .waitFor();
  assert.equal(
    await page
      .getByRole("button", { name: "Translations", exact: true })
      .count(),
    1,
  );
  await page.getByRole("button", { name: "Translations", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Column: region_code zh-Hant", exact: true })
    .waitFor();
  console.log("Dataset editor translation dialog opened");
  assert.equal(
    await page
      .getByRole("textbox", {
        name: "Column: region_code zh-Hant",
        exact: true,
      })
      .inputValue(),
    "繁體 region_code",
  );
  await page.getByRole("button", { name: "Close", exact: true }).last().click();
  await page.goto(
    `http://localhost:8088/superset/dashboard/${fixture.dashboard.id}/?content_locale=zh-Hant`,
    { waitUntil: "domcontentloaded" },
  );
  await page
    .getByRole("columnheader", { name: "繁體 Sample date", exact: true })
    .waitFor({ timeout: 90000 });
  await page.getByRole("tab").filter({ hasText: "繁體 Details" }).waitFor();
  // Native description menu expands a sanitized presentation, with native metadata intact.
  await page.locator(`#slice_${fixture.charts[0].id}-controls`).click();
  await page.getByText("Show chart description", { exact: true }).click();
  await page
    .getByRole("complementary")
    .filter({ hasText: "繁體 Synthetic" })
    .waitFor();
  await page.waitForTimeout(2000);
  const beforeDetails = queries;
  await language("简体中文");
  await page
    .getByRole("columnheader", { name: "简体 Sample date", exact: true })
    .waitFor();
  await page
    .getByRole("complementary")
    .filter({ hasText: "简体 Synthetic" })
    .waitFor();
  assert.equal(queries, beforeDetails);
  await page.getByRole("tab").filter({ hasText: "简体 Trends" }).click();
  await page.getByText("200", { exact: true }).waitFor({ timeout: 90000 });
  await page.waitForTimeout(3000);
  const beforeTrends = queries;
  await language("English");
  await page.getByRole("tab").filter({ hasText: "Trends" }).waitFor();
  assert.equal(
    await page
      .getByRole("tab")
      .filter({ hasText: "Trends" })
      .getAttribute("aria-selected"),
    "true",
  );
  assert.equal(
    queries,
    beforeTrends,
    "Active tab and inactive charts survive locale change",
  );
  await page.getByRole("tab").filter({ hasText: "Details" }).click();
  await page
    .getByRole("columnheader", { name: "Sample date", exact: true })
    .waitFor();
  await page.screenshot({
    path: resolve(root, "test-results/unrelated-dashboard.png"),
    fullPage: true,
  });
  assert.deepEqual(errors, []);
  writeFileSync(
    resolve(root, "test-results/authoring.json"),
    JSON.stringify(
      {
        passed: true,
        chartEditor: true,
        datasetEditor: true,
        unrelatedFiveTypes: true,
        descriptions: true,
        activeTabs: true,
        localeQueries: 0,
        errors,
      },
      null,
      2,
    ),
  );
  console.log(
    "Chart and dataset dialogs, unrelated native charts, descriptions and tab state passed.",
  );
} catch (error) {
  await page.screenshot({
    path: resolve(root, "test-results/authoring-failure.png"),
  });
  writeFileSync(
    resolve(root, "test-results/authoring-failure.json"),
    JSON.stringify(
      { errors, text: await page.locator("body").innerText(), url: page.url() },
      null,
      2,
    ),
  );
  throw error;
} finally {
  await context.close();
  await browser.close();
}
