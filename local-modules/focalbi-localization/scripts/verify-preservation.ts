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
// Reuse the existing read-only test inspector; no production hooks or globals.
const inspect = readFileSync(
  resolve(root, "../focalbi-rendering/tests/native-browser.ts"),
  "utf8",
)
  .match(/const inspect = `([\s\S]+?)`;/)?.[1]
  ?.replace(
    "legend:option?.legend,",
    "legend:option?.legend,graphic:option?.graphic,zoom:option?.dataZoom?.map(item=>({start:item.start,end:item.end,startValue:item.startValue,endValue:item.endValue})),",
  );
assert.ok(inspect);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
page.setDefaultTimeout(60000);
const errors: string[] = [];
let queries = 0;
let nativeRetries = 0;
page.on("pageerror", (error: Error) => errors.push(error.message));
page.on("request", (request: { url(): string }) => {
  if (request.url().includes("/api/v1/chart/data")) queries++;
});
const plotAction = (type: string, action: object) => `(() => {
 const node=document.querySelector('[data-test-viz-type="${type}"]'); const plot=node.querySelector('[_echarts_instance_]');
 let fiber=plot[Object.keys(plot).find(k=>k.startsWith('__reactFiber'))];
 while(fiber){let hook=fiber.memoizedState;while(hook){const ref=hook.memoizedState?.current;if(ref?.dispatchAction){ref.dispatchAction(${JSON.stringify(action)});return}hook=hook.next}fiber=fiber.return}throw new Error('Missing native chart instance');
})()`;
try {
  await page.goto("http://192.168.10.27:3010/#focal-bi", {
    waitUntil: "domcontentloaded",
  });
  await page.waitForTimeout(3000);
  await page.locator("[data-focalbi-embed]").scrollIntoViewIfNeeded();
  await page
    .getByRole("button", { name: "Expand dashboard", exact: true })
    .click();
  let frame;
  for (let attempt = 0; attempt < 120; attempt++) {
    frame = page
      .frames()
      .find((item: { url(): string }) => item.url().includes("/embedded/"));
    if (frame) break;
    await page.waitForTimeout(500);
  }
  assert.ok(frame);
  const waitForNative = async (condition: string) => {
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        await frame.waitForFunction(condition, null, { timeout: 60000 });
        return;
      } catch (error) {
        const failed = frame
          .locator('[data-test="chart-grid-component"]')
          .filter({ hasText: "Request timed out" });
        if (!(await failed.count()) || attempt === 2) throw error;
        const id = await failed.first().getAttribute("data-test-chart-id");
        await frame.locator(`#slice_${id}-controls`).click();
        await frame.getByRole("menuitem", { name: /^Force refresh/ }).click();
        nativeRetries++;
        console.log("Retried an initial native chart-data timeout");
      }
    }
  };
  await frame
    .getByText("72,002,518.80", { exact: true })
    .waitFor({ timeout: 120000 });
  await frame
    .locator('[data-test-viz-type="mixed_timeseries"]')
    .scrollIntoViewIfNeeded();
  await waitForNative(
    `document.querySelectorAll('[_echarts_instance_]').length>=4`,
  );
  console.log("Native charts loaded");
  await page.waitForTimeout(1800);
  const baseline = await frame.evaluate(inspect);
  const company = baseline.filters.find(
    (item: { name: string }) => item.name === "Company",
  );
  const input = frame.getByRole("combobox", { name: company.id, exact: true });
  await input.click();
  await input.fill("OPM");
  await frame
    .locator(".ant-select-dropdown:visible .ant-select-item-option-content")
    .getByText("OPM Systems Company Limited", { exact: true })
    .click();
  await input.press("Escape");
  await frame
    .getByRole("button", { name: "Apply filters", exact: true })
    .click();
  await frame
    .getByText("183,079,390.79", { exact: true })
    .waitFor({ timeout: 120000 });
  await waitForNative(
    `(() => {const state=${inspect};return state.charts.every(chart=>chart.status==='rendered') && state.charts.find(chart=>chart.type==='table').rows[0].length===150})()`,
  );
  await frame.evaluate(
    plotAction("pie", { type: "legendUnSelect", name: "Other contractors" }),
  );
  await frame.evaluate(
    plotAction("mixed_timeseries", { type: "dataZoom", start: 20, end: 80 }),
  );
  await page
    .getByRole("button", { name: "Close expanded view", exact: true })
    .click();
  await page.waitForTimeout(500);
  const table = frame.locator('[data-test-viz-type="table"]');
  await table
    .getByRole("columnheader", { name: "Award Date", exact: true })
    .click();
  await table.locator(".pagination").getByText("2", { exact: true }).click();
  const visibleRecords = () =>
    table
      .locator("tbody tr")
      .evaluateAll((rows: HTMLTableRowElement[]) =>
        rows.map((row) => [
          row.cells[0].textContent,
          row.cells[1].textContent,
          row.cells[3].textContent,
        ]),
      );
  const records = await visibleRecords();
  const applied = await frame.evaluate(inspect);
  console.log("Company selection applied");
  const annual = applied.charts.find(
    (chart: { type: string }) => chart.type === "mixed_timeseries",
  );
  assert.equal(annual.zoom[0].start, 20);
  assert.equal(annual.zoom[0].end, 80);
  assert.deepEqual(
    applied.charts
      .filter((chart: { type: string }) => chart.type === "big_number_total")
      .map(
        (chart: { rows: Record<string, number>[][] }) =>
          Object.values(chart.rows[0][0])[0],
      ),
    [183079390.79, 150, 52],
  );
  const before = queries;
  for (const engine of ["FocalBI fork", "Superset baseline"]) {
    console.log(`Checking engine ${engine}`);
    if (engine === "Superset baseline") {
      await frame
        .locator('[data-test="focalbi-renderer-toolbar"] .ant-select-selector')
        .click();
      await frame
        .locator(".ant-select-dropdown:visible .ant-select-item-option-content")
        .getByText(engine, { exact: true })
        .click();
      await page.waitForTimeout(1500);
      assert.equal(queries, before, "Renderer change makes no chart requests");
    }
    for (const [option, header, locale] of [
      ["繁體", "批出日期", "zh-Hant"],
      ["简体", "批出日期", "zh-Hans"],
      ["English", "Award Date", "en"],
    ]) {
      console.log(`Checking locale ${option}`);
      const metadata = page.waitForResponse(
        (response: { url(): string; status(): number }) =>
          response.status() === 200 &&
          response.url().includes("/catalog/bundle/dashboard/") &&
          new URL(response.url()).searchParams.get("locale") === locale,
      );
      await page
        .getByRole("button", { name: option, exact: true })
        .first()
        .click();
      await (await metadata).finished();
      await table
        .getByRole("columnheader", { name: header, exact: true })
        .waitFor();
      await page.waitForTimeout(1500);
      const current = await frame.evaluate(inspect);
      for (const chart of current.charts.filter(
        (item: { legend?: unknown }) => item.legend,
      )) {
        for (const legend of chart.legend) {
          if (!Array.isArray(legend.selector) || !legend.selector.length)
            continue;
          assert.equal(
            legend.selector.find(
              (item: { type: string }) => item.type === "all",
            )?.title,
            locale === "en" ? "All" : locale === "zh-Hant" ? "全選" : "全选",
          );
          assert.equal(
            legend.selector.find(
              (item: { type: string }) => item.type === "inverse",
            )?.title,
            locale === "en" ? "Inv" : locale === "zh-Hant" ? "反選" : "反选",
          );
        }
      }
      const theme = current.charts.find(
        (item: { type: string; graphic?: unknown[] }) =>
          item.type === "pie" && item.graphic?.length,
      );
      assert.ok(
        JSON.stringify(theme?.graphic).includes(
          locale === "en"
            ? "Total: 150"
            : locale === "zh-Hant"
              ? "總計：150"
              : "总计：150",
        ),
      );
      assert.deepEqual(
        current.charts.map((chart: { rows: unknown }) => chart.rows),
        applied.charts.map((chart: { rows: unknown }) => chart.rows),
      );
      assert.deepEqual(
        current.charts.map((chart: { series: unknown }) => chart.series),
        applied.charts.map((chart: { series: unknown }) => chart.series),
      );
      assert.deepEqual(
        current.charts.find(
          (chart: { type: string }) => chart.type === "mixed_timeseries",
        ).zoom,
        annual.zoom,
        "Native zoom range retained",
      );
      assert.equal(
        current.charts.find((chart: { type: string }) => chart.type === "pie")
          .legend[0].selected["Other contractors"],
        false,
      );
      assert.deepEqual(
        await visibleRecords(),
        records,
        `Date sorting and pagination retained (${engine}, ${option})`,
      );
      assert.equal(queries, before);
    }
  }
  // The localized selector titles retain ECharts' native selection actions.
  await frame.evaluate(plotAction("pie", { type: "legendAllSelect" }));
  await page.waitForTimeout(300);
  let selected = (await frame.evaluate(inspect)).charts.find(
    (chart: { type: string }) => chart.type === "pie",
  ).legend[0].selected;
  assert.ok(Object.values(selected).every((value) => value === true));
  await frame.evaluate(plotAction("pie", { type: "legendInverseSelect" }));
  await page.waitForTimeout(300);
  selected = (await frame.evaluate(inspect)).charts.find(
    (chart: { type: string }) => chart.type === "pie",
  ).legend[0].selected;
  assert.ok(Object.values(selected).every((value) => value === false));
  assert.equal(
    queries,
    before,
    "Legend selector actions stay within native presentation state",
  );
  assert.deepEqual(errors, []);
  writeFileSync(
    resolve(root, "test-results/preservation.json"),
    JSON.stringify(
      {
        passed: true,
        engines: ["fork", "baseline"],
        multiCompanyMetrics: [183079390.79, 150, 52],
        rawQueryData: true,
        series: true,
        legend: true,
        legendSelectorActions: true,
        localizedSelectorTitles: true,
        localizedNativeTotals: true,
        zoomRetention: true,
        dateSort: true,
        pagination: true,
        localeQueries: 0,
        nativeRetries,
        errors,
      },
      null,
      2,
    ),
  );
  console.log(
    "Combined metrics, raw data, series, legend and sorted pagination survived all locales.",
  );
} catch (error) {
  await page.screenshot({
    path: resolve(root, "test-results/preservation-failure.png"),
  });
  const frame = page
    .frames()
    .find((item: { url(): string }) => item.url().includes("/embedded/"));
  writeFileSync(
    resolve(root, "test-results/preservation-failure.json"),
    JSON.stringify(
      {
        errors,
        text: frame
          ? await frame.locator("body").innerText()
          : "No embedded frame",
      },
      null,
      2,
    ),
  );
  throw error;
} finally {
  await browser.close();
}
