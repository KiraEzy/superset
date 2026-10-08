/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership. The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
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
  viewport: { width: 1550, height: 1200 },
});
// Use an ephemeral, assigned-post administrator test session; never a guest token.
await context.addCookies([
  JSON.parse(
    readFileSync(
      process.env.FOCALBI_TEST_SESSION ||
        resolve(root, ".runtime/admin-cookie.json"),
      "utf8",
    ),
  ),
]);
const page = await context.newPage();
const errors: string[] = [];
page.on("pageerror", (e: Error) => errors.push(e.message));
const fixture = JSON.parse(
  readFileSync(resolve(root, ".runtime/resources.json"), "utf8").replace(
    /^\uFEFF/,
    "",
  ),
).resources.find(
  (resource: { key: string }) => resource.key === "native-demographic-test",
);
const url =
  (process.env.FOCALBI_TEST_ORIGIN || "http://192.168.10.27:8088") +
  "/superset/dashboard/" +
  (process.env.FOCALBI_TEST_DASHBOARD_ID || fixture.dashboard.id) +
  "/";
try {
  await page.goto(url);
  await page.waitForFunction(
    `document.querySelectorAll('[data-test="focalbi-chart"] canvas').length===5`,
    null,
    { timeout: 120000 },
  );
  assert.equal(await page.locator('[data-test="focalbi-chart"]').count(), 5);
  await page
    .getByRole("button", { name: "Edit dashboard", exact: true })
    .click();
  await page
    .getByRole("button", { name: "FocalBI presentation settings", exact: true })
    .first()
    .click();
  await page
    .locator(
      '.ant-popover .ant-select[aria-label="Title selection filter"] .ant-select-selector',
    )
    .click();
  await page
    .locator(".ant-select-item-option-content")
    .getByText("District", { exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Single selection title", exact: true })
    .fill("{selection} demographic sample");
  await page
    .getByRole("textbox", { name: "Multiple selections title", exact: true })
    .fill("Demographic sample");
  await page
    .getByRole("button", { name: "Apply presentation settings", exact: true })
    .click();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.waitForTimeout(1500);
  await page.reload();
  await page
    .getByText("Central demographic sample", { exact: true })
    .waitFor({ timeout: 120000 });
  assert.equal(
    await page.locator('[data-test="focalbi-chart"] canvas').count(),
    5,
  );
  await page
    .locator("body")
    .screenshot({ path: resolve(root, "test-results/native-generic.png") });
  await page
    .getByRole("button", { name: "Edit dashboard", exact: true })
    .click();
  await page
    .getByRole("button", { name: "FocalBI presentation settings", exact: true })
    .first()
    .click();
  await page
    .getByRole("textbox", { name: "Single selection title", exact: true })
    .fill("{selection} discarded presentation");
  await page
    .getByRole("button", { name: "Apply presentation settings", exact: true })
    .click();
  await page.getByRole("button", { name: "Discard", exact: true }).click();
  await page.waitForTimeout(1000);
  await page.reload();
  await page
    .getByText("Central demographic sample", { exact: true })
    .waitFor({ timeout: 120000 });
  assert.equal(
    await page
      .getByText("Central discarded presentation", { exact: true })
      .count(),
    0,
  );
  assert.deepEqual(errors, []);
  writeFileSync(
    resolve(root, "test-results/native-editor.json"),
    JSON.stringify(
      {
        passed: true,
        checks: [
          "unrelated native dataset",
          "five native pies without viewer definitions",
          "native editing",
          "presentation popover",
          "native Save persists optional metadata",
          "native Discard restores metadata",
        ],
        errors,
      },
      null,
      2,
    ),
  );
  console.log("Native editor and generic dashboard checks passed.");
} finally {
  await page
    .locator("body")
    .screenshot({ path: resolve(root, "test-results/native-editor-last.png") })
    .catch(() => {});
  await browser.close();
}
