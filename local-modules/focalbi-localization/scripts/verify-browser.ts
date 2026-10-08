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
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdirSync, writeFileSync } from "node:fs";
import assert from "node:assert/strict";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(
  resolve(root, "../../superset-frontend/package.json"),
);
const { chromium } = require("playwright");
mkdirSync(resolve(root, "test-results"), { recursive: true });
mkdirSync(resolve(root, ".runtime"), { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({
  viewport: { width: 1600, height: 1100 },
});
const page = await context.newPage();
page.setDefaultTimeout(30000);
const errors: string[] = [];
let chartRequests = 0;
page.on("request", (request: { url: () => string }) => {
  if (request.url().includes("/api/v1/chart/data")) chartRequests++;
});
page.on("pageerror", (error: Error) => errors.push(error.message));
page.on("console", (message: { type: () => string; text: () => string }) => {
  if (message.type() === "error") errors.push(message.text().slice(0, 500));
});
page.on("requestfailed", (request: { url: () => string }) => {
  if (request.url().includes("extensions"))
    errors.push("Failed extension request: " + request.url());
});
try {
  const origin = process.env.FOCALBI_TEST_ORIGIN || "http://localhost:8088";
  await page.goto(`${origin}/login/`, { waitUntil: "domcontentloaded" });
  console.log("Native login page opened");
  await page
    .locator('input#username, input[name="username"]')
    .fill(process.env.FOCALBI_TEST_USERNAME || "admin");
  await page
    .locator('input#password, input[type="password"]')
    .fill(process.env.FOCALBI_TEST_PASSWORD || "admin");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL((url: URL) => !url.pathname.includes("/login"), {
    timeout: 30000,
  });
  await page.goto(`${origin}/superset/choose-post/`);
  if (
    page.url().includes("choose_post") ||
    page.url().includes("choose-post")
  ) {
    await page
      .getByRole("button", { name: "Login", exact: true })
      .first()
      .click();
    await page.waitForURL(
      (url: URL) =>
        !url.pathname.includes("choose_post") &&
        !url.pathname.includes("choose-post"),
      { timeout: 30000 },
    );
  }
  const cookie = (await context.cookies()).find(
    (cookie: { name: string }) => cookie.name === "session",
  );
  if (!cookie) throw new Error("Native login did not produce a session");
  writeFileSync(
    resolve(root, ".runtime/admin-cookie.json"),
    JSON.stringify(cookie),
  );
  errors.length = 0;
  await page.goto(`${origin}/superset/dashboard/16/?content_locale=zh-Hant`);
  await page
    .getByText("Content language", { exact: true })
    .waitFor({ timeout: 60000 });
  await page
    .locator('[data-test="chart-container"]')
    .first()
    .waitFor({ timeout: 60000 });
  await page
    .getByText("72,002,518.80", { exact: true })
    .waitFor({ timeout: 90000 });
  await page
    .getByRole("columnheader", { name: "批出日期" })
    .waitFor({ timeout: 90000 });
  await page.waitForTimeout(5000);
  const nativeTitle = page.getByRole("textbox", {
    name: "Dashboard title",
    exact: true,
  });
  assert.equal(
    await nativeTitle.inputValue(),
    "政府資訊科技項目批出分析｜公司比較",
  );
  await page.getByRole("button", { name: "Translations", exact: true }).click();
  await page
    .getByText("Save translations", { exact: true })
    .waitFor({ timeout: 60000 });
  const titleInput = page.getByRole("textbox", {
    name: "Dashboard title zh-Hant",
    exact: true,
  });
  await titleInput.waitFor({ timeout: 60000 });
  const savedTitle = await titleInput.inputValue();
  await titleInput.fill("Discarded draft");
  await page.getByRole("button", { name: "Close", exact: true }).last().click();
  await page.getByRole("button", { name: "Translations", exact: true }).click();
  assert.equal(
    await page
      .getByRole("textbox", { name: "Dashboard title zh-Hant", exact: true })
      .inputValue(),
    savedTitle,
  );
  await page
    .getByRole("button", { name: "Save translations", exact: true })
    .click();
  await page
    .getByText(
      "Translations saved. Native resource changes are saved separately.",
    )
    .waitFor({ timeout: 60000 });
  await page.getByRole("button", { name: "Close", exact: true }).last().click();
  const search = page.locator(
    '[data-test-viz-type="table"] .dt-global-filter input',
  );
  await search.fill("Dental");
  await page.waitForTimeout(1000);
  const beforeSwitch = chartRequests;
  for (const [locale, option, heading] of [
    ["zh-Hans", "简体中文", "批出日期"],
    ["en", "English", "Award Date"],
    ["zh-Hant", "繁體中文", "批出日期"],
  ]) {
    await page
      .locator(
        '[data-test="focalbi-localization-toolbar"] .ant-select-selector',
      )
      .click();
    await page
      .locator(".ant-select-dropdown:visible .ant-select-item-option-content")
      .getByText(option, { exact: true })
      .click();
    await page
      .getByRole("columnheader", { name: heading, exact: true })
      .waitFor({ timeout: 60000 });
    await page.waitForTimeout(1500);
    assert.equal(
      await search.inputValue(),
      "Dental",
      `${locale} retains search`,
    );
    assert.equal(
      chartRequests,
      beforeSwitch,
      `${locale} triggers no chart data requests`,
    );
  }
  const renderer = page.locator("#focalbi-renderer");
  if (await renderer.count()) {
    await page
      .locator('[data-test="focalbi-renderer-toolbar"] .ant-select-selector')
      .click();
    await page
      .locator(".ant-select-dropdown:visible .ant-select-item-option-content")
      .getByText("Superset baseline", { exact: true })
      .click();
    await page.waitForTimeout(1500);
    assert.equal(await search.inputValue(), "Dental");
    assert.equal(chartRequests, beforeSwitch);
    await page
      .locator('[data-test="focalbi-renderer-toolbar"] .ant-select-selector')
      .click();
    await page
      .locator(".ant-select-dropdown:visible .ant-select-item-option-content")
      .getByText("FocalBI fork", { exact: true })
      .click();
  }
  await search.fill("");
  await page.screenshot({
    path: resolve(root, "test-results/native-first.png"),
    fullPage: true,
  });
  writeFileSync(
    resolve(root, "test-results/native-first.json"),
    JSON.stringify(
      { errors, text: await page.locator("body").innerText() },
      null,
      2,
    ),
  );
  console.log(
    JSON.stringify({
      login: true,
      languageSelector: true,
      dialog: true,
      unsavedDiscard: true,
      separateSave: true,
      localeSwitchRequests: chartRequests - beforeSwitch,
      errors,
    }),
  );
} catch (error) {
  console.log(
    JSON.stringify({
      errors,
      body: (await page.locator("body").innerText()).slice(0, 2500),
    }),
  );
  await page.screenshot({
    path: resolve(root, "test-results/native-failure.png"),
  });
  throw error;
} finally {
  await context.close();
  await browser.close();
}
