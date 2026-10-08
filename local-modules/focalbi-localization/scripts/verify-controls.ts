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
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(
  resolve(root, "../../superset-frontend/package.json"),
);
const { chromium } = require("playwright");
const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({
  viewport: { width: 1600, height: 1100 },
});
await context.addCookies([
  JSON.parse(readFileSync(resolve(root, ".runtime/admin-cookie.json"), "utf8")),
]);
const page = await context.newPage();
page.setDefaultTimeout(60000);
page.setDefaultNavigationTimeout(180000);
const errors: string[] = [];
let queries = 0;
page.on("pageerror", (error: Error) => errors.push(error.message));
page.on("request", (request: { url(): string }) => {
  if (request.url().includes("/api/v1/chart/data")) queries++;
});
async function language(label: string, locale: string) {
  const metadata = page.waitForResponse(
    (response: { url(): string; status(): number }) =>
      response.status() === 200 &&
      response.url().includes("/catalog/bundle/dashboard/") &&
      new URL(response.url()).searchParams.get("locale") === locale,
  );
  await page
    .locator('[data-test="focalbi-localization-toolbar"] .ant-select-selector')
    .first()
    .click();
  await page
    .locator(".ant-select-dropdown:visible .ant-select-item-option-content")
    .getByText(label, { exact: true })
    .click();
  await (await metadata).finished();
  await page.waitForTimeout(1200);
}
try {
  await page.goto(
    "http://localhost:8088/superset/dashboard/16/?content_locale=zh-Hant",
    { waitUntil: "domcontentloaded" },
  );
  console.log("Native dashboard opened");
  const table = page.locator('[data-test-viz-type="table"]');
  await table.scrollIntoViewIfNeeded();
  await table
    .getByRole("columnheader", { name: "批出日期", exact: true })
    .waitFor({ timeout: 120000 });
  console.log("Localized source table loaded");
  assert.ok(await page.getByText("篩選與控制", { exact: true }).count());
  assert.ok(
    await page
      .getByRole("button", { name: "套用篩選", exact: true })
      .isDisabled(),
  );
  assert.ok(
    await page.getByText("Dashboards", { exact: true }).count(),
    "Native app navigation retains its UI language",
  );
  const size = table.getByRole("combobox", {
    name: "每頁顯示筆數",
    exact: true,
  });
  assert.equal(await size.count(), 1);
  await table.locator(".dt-select-page-size .ant-select-selector").click();
  await page
    .locator(".ant-select-dropdown:visible .ant-select-item-option-content")
    .getByText("20", { exact: true })
    .click();
  await page.waitForFunction(
    () =>
      document.querySelectorAll('[data-test-viz-type="table"] tbody tr')
        .length === 20,
  );
  assert.equal(await table.locator("tbody tr").count(), 20);
  console.log("Localized page size works");
  const search = table.locator(".dt-global-filter input");
  await search.fill("__unmatched_localization_test__");
  await table.getByText("找不到符合條件的資料", { exact: true }).waitFor();
  console.log("Localized empty search works");
  const before = queries;
  await language("简体中文", "zh-Hans");
  assert.equal(queries, before);
  assert.ok(await page.getByText("筛选与控制", { exact: true }).count());
  assert.equal(await search.inputValue(), "__unmatched_localization_test__");
  assert.equal(await search.getAttribute("aria-label"), "搜索 53 条记录");
  assert.ok(
    await table.getByText("找不到符合条件的记录", { exact: true }).count(),
  );
  assert.ok(
    (await table.locator(".dt-select-page-size").innerText()).includes("20"),
  );
  await language("English", "en");
  assert.equal(queries, before);
  assert.ok(
    await table.getByText("No matching records found", { exact: true }).count(),
  );
  await search.fill("");
  await page.waitForTimeout(800);
  assert.equal(await table.locator("tbody tr").count(), 20);
  await page.getByText("Value: lowest first", { exact: true }).click();
  await page.waitForTimeout(1500);
  await page.getByText("Value: highest first", { exact: true }).click();
  await page.waitForTimeout(1500);
  await page.getByRole("button", { name: "Clear all", exact: true }).click();
  await page.waitForTimeout(1000);
  // Read an existing unrelated resource; no definitions or catalogs are edited.
  console.log("Checking unrelated dashboard");
  await page.goto(
    "http://localhost:8088/superset/dashboard/18/?content_locale=zh-Hant",
    { waitUntil: "domcontentloaded" },
  );
  await page
    .getByText("篩選與控制", { exact: true })
    .waitFor({ timeout: 120000 });
  assert.ok(
    await page
      .getByText("Hong Kong Census 2021 - People, Households and Districts", {
        exact: true,
      })
      .count(),
    "Untranslated authored title remains original",
  );
  await page
    .getByText("7,411,945", { exact: true })
    .first()
    .waitFor({ timeout: 120000 });
  await page.waitForTimeout(4000);
  const otherBefore = queries;
  await language("简体中文", "zh-Hans");
  assert.equal(queries, otherBefore);
  assert.ok(await page.getByText("筛选与控制", { exact: true }).count());
  await page.screenshot({
    path: resolve(root, "test-results/controls-unrelated.png"),
  });
  assert.deepEqual(errors, []);
  const mode = process.argv.includes("--rendering") ? "combined" : "native";
  writeFileSync(
    resolve(root, `test-results/controls-${mode}.json`),
    JSON.stringify(
      {
        passed: true,
        filterControls: true,
        pageSize: true,
        emptySearch: true,
        localeQueries: 0,
        nativeUiIndependent: true,
        sortControls: true,
        unrelatedResource: true,
        errors,
      },
      null,
      2,
    ),
  );
  console.log(
    `Dashboard controls passed (${mode}); unrelated resource and native UI isolation verified.`,
  );
} catch (error) {
  writeFileSync(
    resolve(root, "test-results/controls-failure.json"),
    JSON.stringify(
      { errors, url: page.url(), text: await page.locator("body").innerText() },
      null,
      2,
    ),
  );
  await page.screenshot({
    path: resolve(root, "test-results/controls-failure.png"),
  });
  throw error;
} finally {
  await context.close();
  await browser.close();
}
