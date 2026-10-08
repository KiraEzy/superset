/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership. The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License. You may obtain a copy of the License at
 * http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { Frame } from "../../../superset-frontend/node_modules/playwright";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(
  resolve(root, "../../superset-frontend/package.json"),
);
const { chromium } = require("playwright");
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
page.setDefaultTimeout(30000);
const output = resolve(root, "test-results/filter-actions");
mkdirSync(output, { recursive: true });
const results: string[] = [];
const errors: string[] = [];
let serverSearches = 0;
page.on("request", (request: { url(): string; postData(): string | null }) => {
  if (
    request.url().includes("/api/v1/chart/data") &&
    request.postData()?.includes("Accentrix")
  )
    serverSearches++;
});
page.on("pageerror", (error: Error) => errors.push(error.message));
const base = new URL(
  process.env.FOCALBI_TEST_URL || "http://192.168.10.27:3040/en/p/focal-bi",
);
async function open(locale: string, expand: string): Promise<Frame> {
  const url = new URL(base);
  url.pathname = url.pathname.replace(
    /^\/(en|zh-Hant|zh-Hans)\//,
    `/${locale}/`,
  );
  await page.goto(url.href, { waitUntil: "domcontentloaded" });
  await page.locator('.fds-bi-toolbar button[aria-expanded="false"]').click();
  for (let attempt = 0; attempt < 120; attempt++) {
    const frame = page
      .frames()
      .find((item: Frame) => item.url().includes("/embedded/"));
    if (frame) {
      await frame
        .getByText("72,002,518.80", { exact: true })
        .waitFor({ timeout: 120000 });
      return frame;
    }
    await page.waitForTimeout(500);
  }
  throw new Error("Dashboard iframe did not mount");
}
try {
  const frame = await open("en", "Expand dashboard");
  const company = frame.getByRole("combobox", {
    name: "NATIVE_FILTER-MCP-51dd6fe50c67",
    exact: true,
  });
  const toolbar = frame.locator(
    '[data-test="focalbi-filter-dropdown"]:visible',
  );
  const all = toolbar.getByRole("button", { name: /^Select all/ });
  const clear = toolbar.getByRole("button", { name: /^Clear/ });
  const apply = frame.getByRole("button", {
    name: "Apply filters",
    exact: true,
  });
  await company.click();
  await all.waitFor();
  const companyField = frame.locator(".ant-select").filter({ has: company });
  await companyField.hover();
  assert.equal(
    await companyField.locator(".ant-select-clear").count(),
    0,
    "No hover-only whole-field clear icon",
  );
  assert.ok(
    await companyField.locator(".ant-select-selection-item-remove").count(),
    "Individual tag removal remains available",
  );
  assert.equal(await clear.innerText(), "Clear (1)");
  await page.screenshot({ path: resolve(output, "en-dropdown.png") });
  await company.press("Tab");
  assert.ok(
    await all.evaluate((el: HTMLElement) => el === document.activeElement),
    "Tab reaches Select all without selecting a row",
  );
  await all.press("Tab");
  assert.ok(
    await clear.evaluate((el: HTMLElement) => el === document.activeElement),
    "Tab reaches Clear",
  );
  await clear.press("Tab");
  await toolbar.waitFor({ state: "hidden" });
  assert.equal(
    await frame.evaluate(() => document.activeElement?.id),
    "NATIVE_FILTER-MCP-ee9eab48b91d",
    "Tab exits to the next filter",
  );
  await company.click();
  await company.press("Tab");
  await all.press("Tab");
  await clear.press("Enter");
  await page.waitForTimeout(400);
  assert.equal(await clear.innerText(), "Clear (0)");
  assert.ok(
    await apply.isDisabled(),
    "Required Company cannot be applied empty",
  );
  await page.screenshot({ path: resolve(output, "required-empty.png") });
  results.push(
    "Keyboard Tab/Enter Clear; empty required filter cannot be applied",
  );
  await company.fill("Accentrix");
  await page.waitForTimeout(1800);
  assert.ok(
    serverSearches > 0,
    "Native server search still requests matching options before Apply",
  );
  assert.equal(await all.innerText(), "Select all (1)");
  await company.press("Tab");
  await all.press("Space");
  await page.waitForTimeout(300);
  assert.equal(await clear.innerText(), "Clear (1)");
  assert.equal(await all.innerText(), "Select all (0)");
  await clear.press("Escape");
  await toolbar.waitFor({ state: "hidden" });
  assert.ok(
    await company.evaluate((el: HTMLElement) => el === document.activeElement),
    "Escape returns focus to filter",
  );
  assert.ok(
    await frame.getByText("72,002,518.80", { exact: true }).isVisible(),
    "Draft does not change KPI",
  );
  assert.ok(await apply.isEnabled());
  await apply.click();
  await frame
    .getByText("Accentrix Company Limited awarded value (HKD)", { exact: true })
    .waitFor();
  results.push(
    "Keyboard Space selects matching company; Escape closes; native Apply updates charts",
  );
  await company.click();
  await company.fill("FDS");
  await page.waitForTimeout(1800);
  assert.equal(await all.innerText(), "Select all (1)");
  await all.click();
  assert.equal(
    await clear.innerText(),
    "Clear (2)",
    "Search adds to previous off-search selection",
  );
  await page.screenshot({ path: resolve(output, "search-selection.png") });
  await company.fill("__no_company_matches__");
  await page.waitForTimeout(1800);
  assert.ok(await all.isDisabled());
  await clear.click();
  assert.equal(
    await clear.innerText(),
    "Clear (0)",
    "Clear empties field even while search hides selected values",
  );
  await company.fill("FDS");
  await page.waitForTimeout(1800);
  await all.click();
  await company.press("Escape");
  await apply.click();
  await frame.getByText("72,002,518.80", { exact: true }).waitFor();
  results.push(
    "Search union, no-match disabled, whole-field Clear and restoring native selection",
  );
  const year = frame.getByRole("combobox", {
    name: "NATIVE_FILTER-MCP-0dadc00f91b3",
    exact: true,
  });
  await year.click();
  assert.equal(await all.innerText(), "Select all (5)");
  await all.click();
  assert.equal(await clear.innerText(), "Clear (5)");
  await page.screenshot({ path: resolve(output, "year-selection.png") });
  assert.ok(await all.isDisabled());
  await clear.click();
  assert.equal(await clear.innerText(), "Clear (0)");
  await year.press("Escape");
  results.push(
    "All five years selected and cleared; repeated Select all disabled",
  );
  await frame
    .locator(".ant-select-selector")
    .filter({ has: frame.locator("#focalbi-renderer") })
    .click();
  await frame.getByText("Superset baseline", { exact: true }).click();
  await company.click();
  await all.waitFor();
  await page.screenshot({ path: resolve(output, "baseline-dropdown.png") });
  await clear.click();
  assert.ok(await apply.isDisabled());
  await company.fill("FDS");
  await page.waitForTimeout(1800);
  await all.click();
  await company.press("Escape");
  results.push(
    "Superset baseline renderer retains identical shortcuts and validation",
  );
  for (const [locale, expand, selectLabel, clearLabel] of [
    ["zh-Hant", "放大儀表板", "全選", "清除"],
    ["zh-Hans", "放大仪表板", "全选", "清除"],
  ]) {
    const localized = await open(locale, expand);
    await page.waitForTimeout(3000);
    await localized
      .getByRole("combobox", {
        name: "NATIVE_FILTER-MCP-51dd6fe50c67",
        exact: true,
      })
      .click();
    const dropdown = localized.locator(
      '[data-test="focalbi-filter-dropdown"]:visible',
    );
    await dropdown
      .getByRole("button", { name: new RegExp(`^${selectLabel}`) })
      .waitFor();
    assert.equal(
      await dropdown
        .getByRole("button", { name: new RegExp(`^${clearLabel}`) })
        .innerText(),
      `${clearLabel} (1)`,
    );
    // Catalog/iframe layout can settle while the first screenshot waits for fonts.
    // Reopen if that native refresh closed the menu, then verify the captured state.
    for (let attempt = 0; attempt < 3; attempt++) {
      if (!(await dropdown.isVisible()))
        await localized
          .getByRole("combobox", {
            name: "NATIVE_FILTER-MCP-51dd6fe50c67",
            exact: true,
          })
          .click();
      await dropdown
        .getByRole("button", { name: new RegExp(`^${selectLabel}`) })
        .hover();
      await page.screenshot({
        path: resolve(output, `${locale}-dropdown.png`),
      });
      if (await dropdown.isVisible()) break;
    }
    assert.ok(
      await dropdown.isVisible(),
      "Localized screenshot retains the open menu",
    );
    results.push(`${locale} translated actions on guest published page`);
  }
  assert.deepEqual(errors, [], "No browser runtime errors");
  writeFileSync(
    resolve(output, "results.json"),
    JSON.stringify({ status: "PASS", results, errors }, null, 2),
  );
  console.log(results.join("\n"));
} catch (error) {
  await page.screenshot({ path: resolve(output, "failure.png") });
  writeFileSync(
    resolve(output, "results.json"),
    JSON.stringify(
      { status: "FAIL", results, error: String(error), errors },
      null,
      2,
    ),
  );
  throw error;
} finally {
  await browser.close();
}
