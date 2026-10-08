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
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { writeFileSync } from "node:fs";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(
  resolve(root, "../../superset-frontend/package.json"),
);
const { chromium } = require("playwright");
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
let issued = 0;
const errors: string[] = [];
page.on("pageerror", (e: Error) => errors.push(e.message));
page.on("response", (response: { url(): string; status(): number }) => {
  if (
    response.url().endsWith("/api/focalbi/guest-token") &&
    response.status() === 200
  )
    issued++;
});
try {
  await page.goto(
    process.env.FOCALBI_TEST_URL || "http://192.168.10.27:3010/#focal-bi",
  );
  await page.locator("iframe").first().scrollIntoViewIfNeeded();
  const deadline = Date.now() + 370000;
  while (issued < 2 && Date.now() < deadline) await page.waitForTimeout(1000);
  assert.ok(issued >= 2, "SDK renews the guest token automatically");
  const frame = page
    .frames()
    .find((f: { url(): string }) => f.url().includes("/embedded/"));
  assert.ok(frame);
  assert.ok(await frame.getByText("72,002,518.80", { exact: true }).count());
  assert.deepEqual(errors, []);
  writeFileSync(
    resolve(root, "test-results/native-renewal.json"),
    JSON.stringify(
      {
        passed: true,
        tokenResponses: issued,
        checks: [
          "native Embedded SDK automatic renewal",
          "approved dashboard remains rendered",
        ],
        errors,
      },
      null,
      2,
    ),
  );
  console.log("Native SDK automatic renewal passed.");
} finally {
  await browser.close();
}
