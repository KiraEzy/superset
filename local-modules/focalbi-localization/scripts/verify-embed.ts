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
import type { Frame } from "../../../superset-frontend/node_modules/playwright";
import { mkdirSync, writeFileSync } from "node:fs";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(
  resolve(root, "../../superset-frontend/package.json"),
);
const { chromium } = require("playwright");
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
page.setDefaultTimeout(60000);
const errors: string[] = [];
let queries = 0;
let nativeRetries = 0;
async function waitForPlots(target: Frame) {
  await target
    .locator('[data-test-viz-type="mixed_timeseries"]')
    .scrollIntoViewIfNeeded();
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await target.waitForFunction(
        () => document.querySelectorAll("[_echarts_instance_]").length >= 4,
        null,
        { timeout: 60000 },
      );
      return;
    } catch (error) {
      const failed = target
        .locator('[data-test="chart-grid-component"]')
        .filter({ hasText: "Request timed out" });
      if (!(await failed.count()) || attempt === 2) throw error;
      const id = await failed.first().getAttribute("data-test-chart-id");
      await target.locator(`#slice_${id}-controls`).click();
      await target.getByRole("menuitem", { name: /^Force refresh/ }).click();
      nativeRetries++;
    }
  }
}
async function waitForTable(target: Frame, label: string) {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await target
        .getByRole("columnheader", { name: label, exact: true })
        .waitFor({ timeout: 60000 });
      return;
    } catch (error) {
      if (attempt === 2) throw error;
      const failed = target
        .locator('[data-test-viz-type="table"]')
        .filter({ hasText: "Request timed out" });
      if (await failed.count()) {
        const id = await failed.first().getAttribute("data-test-chart-id");
        await target.locator(`#slice_${id}-controls`).click();
        await target.getByRole("menuitem", { name: /^Force refresh/ }).click();
        nativeRetries++;
      }
    }
  }
}
page.on("pageerror", (error: Error) => errors.push(error.message));
page.on("request", (request: { url(): string }) => {
  if (request.url().includes("/api/v1/chart/data")) queries++;
});
mkdirSync(resolve(root, "test-results"), { recursive: true });
try {
  await page.goto(
    process.env.FOCALBI_TEST_URL || "http://192.168.10.27:3010/#focal-bi",
    { waitUntil: "domcontentloaded" },
  );
  await page.waitForTimeout(3000);
  await page.locator("[data-focalbi-embed]").scrollIntoViewIfNeeded();
  await page
    .getByRole("button", { name: "Expand dashboard", exact: true })
    .click();
  const deadline = Date.now() + 120000;
  let frame;
  while (Date.now() < deadline) {
    frame = page
      .frames()
      .find((item: { url(): string }) => item.url().includes("/embedded/"));
    if (frame) break;
    await page.waitForTimeout(500);
  }
  assert.ok(frame, "SDK iframe mounted");
  await frame
    .getByText("72,002,518.80", { exact: true })
    .waitFor({ timeout: 120000 });
  await waitForPlots(frame);
  await page
    .getByRole("button", { name: "Close expanded view", exact: true })
    .click();
  await frame.locator('[data-test-viz-type="table"]').scrollIntoViewIfNeeded();
  await waitForTable(frame, "Award Date");
  await page.waitForTimeout(5000);
  const outerHandle = await page
    .locator('iframe[src*="focalbi-embed.html"]')
    .elementHandle();
  const outer = page
    .frames()
    .find((item: { url(): string }) =>
      item.url().includes("focalbi-embed.html"),
    );
  const innerHandle = await outer.locator("iframe").elementHandle();
  const search = frame.locator(
    '[data-test-viz-type="table"] .dt-global-filter input',
  );
  await search.fill("Dental");
  const before = queries;
  for (const [button, locale, name] of [
    ["繁體", "zh-Hant", "批出日期"],
    ["简体", "zh-Hans", "批出日期"],
    ["English", "en", "Award Date"],
  ]) {
    await page
      .getByRole("button", { name: button, exact: true })
      .first()
      .click();
    await frame
      .getByRole("columnheader", { name, exact: true })
      .waitFor({ timeout: 60000 });
    await page.waitForTimeout(2000);
    const controls =
      locale === "en"
        ? {
            heading: "Filters and controls",
            apply: "Apply filters",
            search: "Search 53 records",
            option: "5 options",
            size: "Show entries per page",
            renderer: "Renderer",
            desc: "Value: highest first",
          }
        : locale === "zh-Hant"
          ? {
              heading: "篩選與控制",
              apply: "套用篩選",
              search: "搜尋 53 筆資料",
              option: "5 個選項",
              size: "每頁顯示筆數",
              renderer: "圖表呈現引擎",
              desc: "數值：由高至低",
            }
          : {
              heading: "筛选与控制",
              apply: "应用筛选",
              search: "搜索 53 条记录",
              option: "5 个选项",
              size: "每页显示条数",
              renderer: "图表渲染引擎",
              desc: "数值：从高到低",
            };
    assert.equal(
      await frame.getByText(controls.heading, { exact: true }).count(),
      1,
    );
    assert.ok(
      await frame
        .getByRole("button", { name: controls.apply, exact: true })
        .isDisabled(),
    );
    assert.equal(await search.getAttribute("aria-label"), controls.search);
    assert.equal(
      await frame
        .getByRole("combobox", { name: controls.size, exact: true })
        .count(),
      1,
    );
    assert.ok(await frame.getByText(controls.option, { exact: true }).count());
    assert.equal(
      await frame.getByText(controls.renderer, { exact: true }).count(),
      1,
    );
    assert.equal(
      await frame.getByText(controls.desc, { exact: true }).count(),
      1,
    );
    assert.equal(
      await search.inputValue(),
      "Dental",
      `${locale} preserves search`,
    );
    assert.equal(queries, before, `${locale} makes no chart requests`);
    assert.ok(
      await outerHandle.evaluate((node: HTMLElement) => node.isConnected),
      "outer iframe retained",
    );
    assert.ok(
      await innerHandle.evaluate((node: HTMLElement) => node.isConnected),
      "inner iframe retained",
    );
    assert.ok(page.frames().includes(frame), "SDK frame object retained");
    if (locale === "zh-Hant")
      await page.screenshot({
        path: resolve(root, "test-results/lan-embed-hant.png"),
      });
  }
  // A message from the page itself must not impersonate its SDK parent.
  await frame.evaluate(
    `window.postMessage({type:'focalbi-content-locale',version:1,action:'set',locale:'zh-Hans',requestId:999},location.origin)`,
  );
  await page.waitForTimeout(1000);
  assert.ok(
    await frame
      .getByRole("columnheader", { name: "Award Date", exact: true })
      .count(),
  );
  await page
    .getByRole("button", { name: "Expand dashboard", exact: true })
    .click();
  const renderer = frame.locator(
    '[data-test="focalbi-renderer-toolbar"] .ant-select-selector',
  );
  await renderer.click();
  await frame
    .locator(".ant-select-dropdown:visible .ant-select-item-option-content")
    .getByText("Superset baseline", { exact: true })
    .click();
  await page.waitForTimeout(1500);
  assert.equal(queries, before);
  assert.equal(await search.inputValue(), "Dental");
  await renderer.click();
  await frame
    .locator(".ant-select-dropdown:visible .ant-select-item-option-content")
    .getByText("FocalBI fork", { exact: true })
    .click();
  await page.waitForTimeout(1500);
  assert.equal(queries, before);
  assert.equal(await search.inputValue(), "Dental");
  await search.fill("");
  await page.screenshot({
    path: resolve(root, "test-results/lan-embed-en.png"),
  });
  await page
    .getByRole("button", { name: "Close expanded view", exact: true })
    .click();
  await page.evaluate(() => {
    const second = document.createElement("iframe");
    second.id = "localization-parallel-test";
    second.src = "/focalbi-embed.html?content_locale=zh-Hant";
    second.width = "1400";
    second.height = "1800";
    document.body.append(second);
  });
  await page.locator("#localization-parallel-test").scrollIntoViewIfNeeded();
  let second;
  const parallelDeadline = Date.now() + 120000;
  while (Date.now() < parallelDeadline) {
    second = page
      .frames()
      .find(
        (candidate: { url(): string }) =>
          candidate !== frame &&
          candidate.url().includes("/embedded/") &&
          candidate.url().includes("zh-Hant"),
      );
    if (second) break;
    await page.waitForTimeout(500);
  }
  assert.ok(second, "Second embed mounted with independent URL locale");
  await waitForPlots(second);
  await second.locator('[data-test-viz-type="table"]').scrollIntoViewIfNeeded();
  await waitForTable(second, "批出日期");
  assert.ok(
    await frame
      .getByRole("columnheader", { name: "Award Date", exact: true })
      .count(),
  );
  await page.waitForTimeout(2000);
  const beforeParallel = queries;
  await page
    .locator("#localization-parallel-test")
    .evaluate((iframe: HTMLIFrameElement) =>
      iframe.contentWindow?.postMessage(
        {
          type: "focalbi-content-locale",
          version: 1,
          action: "set",
          locale: "zh-Hans",
        },
        location.origin,
      ),
    );
  await second.getByText("项目主题", { exact: true }).first().waitFor();
  await page.waitForTimeout(1500);
  assert.equal(
    queries,
    beforeParallel,
    "Independent embed switching makes no chart requests",
  );
  assert.ok(
    await frame
      .getByRole("columnheader", { name: "Award Date", exact: true })
      .count(),
  );
  await page
    .locator("#localization-parallel-test")
    .evaluate((iframe: HTMLIFrameElement) => iframe.remove());
  const token = await page.evaluate(async () => {
    const response = await fetch("/api/focalbi/guest-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    return (await response.json()).token as string;
  });
  const supersetOrigin = new URL(frame.url()).origin;
  const identity = await page.request.get(
    `${supersetOrigin}/extensions/focalbi/content-localization/catalog/resolve/dashboard/16`,
    { headers: { "X-GuestToken": token } },
  );
  assert.equal(identity.status(), 200);
  const uid = (await identity.json()).result.uuid;
  const bundle = await page.request.get(
    `${supersetOrigin}/extensions/focalbi/content-localization/catalog/bundle/dashboard/${uid}?locale=zh-Hant`,
    { headers: { "X-GuestToken": token } },
  );
  assert.equal(bundle.status(), 200);
  const author = await page.request.get(
    `${supersetOrigin}/extensions/focalbi/content-localization/catalog/resource/dashboard/${uid}`,
    { headers: { "X-GuestToken": token } },
  );
  assert.equal(author.status(), 403);
  const deniedExport = await page.request.get(
    `${supersetOrigin}/extensions/focalbi/content-localization/catalog/export/dashboard/${uid}`,
    { headers: { "X-GuestToken": token } },
  );
  assert.equal(deniedExport.status(), 403);
  const incorrect = await page.request.get(
    `${supersetOrigin}/extensions/focalbi/content-localization/catalog/resolve/dashboard/18`,
    { headers: { "X-GuestToken": token } },
  );
  assert.equal(incorrect.status(), 403);
  const deniedWrite = await page.request.put(
    `${supersetOrigin}/extensions/focalbi/content-localization/catalog/resource/dashboard/${uid}`,
    { headers: { "X-GuestToken": token }, data: { revision: 0, entries: {} } },
  );
  assert.ok([400, 403].includes(deniedWrite.status()));
  assert.deepEqual(errors, []);
  writeFileSync(
    resolve(root, "test-results/lan-embed.json"),
    JSON.stringify(
      {
        passed: true,
        locales: ["en", "zh-Hant", "zh-Hans"],
        localeChartRequests: 0,
        simultaneousEmbeds: true,
        dashboardControls: true,
        allPlotsLoaded: true,
        nativeRetries,
        frameRetention: true,
        searchRetention: true,
        rendererSwitch: true,
        guestIsolation: true,
        deniedWrites: true,
        wrongSourceMessageIgnored: true,
        errors,
      },
      null,
      2,
    ),
  );
  console.log(
    "LAN embed locale, state, renderer and guest isolation checks passed.",
  );
} catch (error) {
  await page.screenshot({
    path: resolve(root, "test-results/lan-embed-failure.png"),
  });
  writeFileSync(
    resolve(root, "test-results/lan-embed-failure.json"),
    JSON.stringify(
      {
        errors,
        text: await page.locator("body").innerText(),
        frames: page.frames().map((item: { url(): string }) => item.url()),
      },
      null,
      2,
    ),
  );
  throw error;
} finally {
  await browser.close();
}
