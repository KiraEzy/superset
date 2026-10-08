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
const settings = JSON.parse(
  readFileSync(resolve(root, ".runtime/settings.json"), "utf8").replace(
    /^\uFEFF/,
    "",
  ),
);
const origin = process.env.FOCALBI_TEST_HOST || "http://192.168.10.27:3010";
const active = process.env.FOCALBI_TEST_MODE === "active";
const evidence = active ? "native-activation" : "native-rollback";
const config = await (await fetch(origin + "/api/focalbi/config")).json();
assert.equal(
  config.dashboardUuid,
  (active ? settings.native_embed : settings.original_embed).dashboardUuid,
);
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage({
    viewport: { width: 1500, height: 1100 },
  });
  const errors: string[] = [];
  page.on("pageerror", (error: Error) => errors.push(error.message));
  await page.goto(origin + "/#focal-bi");
  await page.locator("iframe").first().scrollIntoViewIfNeeded();
  await page
    .getByRole("button", { name: "Expand dashboard", exact: true })
    .click();
  let frame;
  for (let index = 0; index < 100; index++) {
    frame = page
      .frames()
      .find((frame: { url(): string }) => frame.url().includes("/embedded/"));
    if (frame) break;
    await page.waitForTimeout(1000);
  }
  assert.ok(frame);
  await frame
    .getByText("72,002,518.80", { exact: true })
    .waitFor({ timeout: 120000 });
  if (active) {
    await frame.waitForFunction(
      `document.querySelectorAll('[data-test="focalbi-chart"] canvas').length===4`,
      null,
      { timeout: 120000 },
    );
  }
  assert.equal(
    await frame.locator('[data-test="focalbi-renderer-toolbar"]').count(),
    active ? 1 : 0,
  );
  assert.equal(
    await frame.locator('[data-test="focalbi-chart"]').count(),
    active ? 8 : 0,
  );
  if (active)
    assert.ok(await frame.getByText("FocalBI fork", { exact: true }).count());
  assert.ok(await frame.getByText("53", { exact: true }).count());
  assert.ok(await frame.getByText("19", { exact: true }).count());
  assert.deepEqual(errors, []);
  await frame
    .locator("body")
    .screenshot({ path: resolve(root, `test-results/${evidence}.png`) });
  writeFileSync(
    resolve(root, `test-results/${evidence}.json`),
    JSON.stringify(
      {
        passed: true,
        checks: [
          active
            ? "approved company embed restored"
            : "original approved embed restored",
          "FDS baseline KPIs",
          active
            ? "fork overlay active"
            : "native image renderer without overlay",
        ],
        errors,
      },
      null,
      2,
    ),
  );
  console.log(`${evidence} checks passed.`);
} finally {
  await browser.close();
}
