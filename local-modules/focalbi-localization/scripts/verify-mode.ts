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
const locale = process.argv.includes("--localization");
const renderer = process.argv.includes("--rendering");
const mode = locale
  ? renderer
    ? "both"
    : "localization"
  : renderer
    ? "rendering"
    : "neither";
const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({
  viewport: { width: 1600, height: 1100 },
});
await context.addCookies([
  JSON.parse(readFileSync(resolve(root, ".runtime/admin-cookie.json"), "utf8")),
]);
const page = await context.newPage();
const errors: string[] = [];
page.on("pageerror", (error: Error) => errors.push(error.message));
try {
  // Both modes use the same saved dashboard, datasource and native requests.
  await page.goto(
    "http://localhost:8088/superset/dashboard/16/?content_locale=en",
    { waitUntil: "domcontentloaded" },
  );
  await page
    .getByText("72,002,518.80", { exact: true })
    .waitFor({ timeout: 120000 });
  await page
    .getByRole("columnheader", { name: "Award Date", exact: true })
    .waitFor({ timeout: 120000 });
  assert.equal(
    await page.getByText("Content language", { exact: true }).count(),
    Number(locale),
  );
  assert.equal(
    await page.locator('[data-test="focalbi-renderer-toolbar"]').count(),
    Number(renderer),
  );
  assert.deepEqual(errors, []);
  writeFileSync(
    resolve(root, `test-results/mode-${mode}.json`),
    JSON.stringify(
      { passed: true, mode, nativeValue: "72,002,518.80", errors },
      null,
      2,
    ),
  );
  console.log(`Independent activation mode ${mode} passed.`);
} catch (error) {
  await page.screenshot({
    path: resolve(root, `test-results/mode-${mode}-failure.png`),
  });
  throw error;
} finally {
  await context.close();
  await browser.close();
}
