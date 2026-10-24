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
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(
  resolve(root, "../../superset-frontend/package.json"),
);
const { chromium } = require("playwright");
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1500, height: 1100 } });
// Switching remains opt-in; ordinary viewers use the fork without the toolbar.
await page.addInitScript(() => {
  localStorage.setItem("focalbi.rendererSelector", "true");
});
const errors: string[] = [];
let queries = 0;
page.on("pageerror", (error: Error) => errors.push(error.message));
page.on("request", (request: { url(): string; method(): string }) => {
  if (
    request.method() === "POST" &&
    request.url().includes("/api/v1/chart/data")
  )
    queries++;
});
mkdirSync(resolve(root, "test-results"), { recursive: true });

// Test instrumentation reads the native store and renderer objects. No application
// debug globals, custom endpoints or production query hooks are installed.
const inspect = `(() => {
 const node=document.querySelector('[data-test="focalbi-chart"]');
 let fiber=node[Object.keys(node).find(k=>k.startsWith('__reactFiber'))],store;
 while(fiber){if(fiber.memoizedProps?.value?.store){store=fiber.memoizedProps.value.store;break}fiber=fiber.return}
 const state=store.getState();
 const charts=[...document.querySelectorAll('[data-test="chart-grid-component"]')].map(chart=>{
  const id=chart.getAttribute('data-test-chart-id'),native=state.charts[id];
  const plot=chart.querySelector('[_echarts_instance_]');let option;
  if(plot){let f=plot[Object.keys(plot).find(k=>k.startsWith('__reactFiber'))];
   while(f&&!option){let hook=f.memoizedState;while(hook){const ref=hook.memoizedState?.current;if(ref?.getOption){option=ref.getOption();break}hook=hook.next}f=f.return}}
  return {id,name:chart.getAttribute('data-test-chart-name'),type:chart.getAttribute('data-test-viz-type'),status:native?.chartStatus,
    title:chart.querySelector('.header-title')?.textContent,rows:native?.queriesResponse?.map(q=>q.data),
    series:option?.series.map(s=>({type:s.type,name:s.name,data:s.data,z:s.z,areaStyle:s.areaStyle})),legend:option?.legend,
    filters:native?.latestQueryFormData?.extra_form_data?.filters};
 });
 return {charts,filters:Object.values(state.nativeFilters.filters),mask:state.dataMask};
})()`;

try {
  await page.goto(
    process.env.FOCALBI_TEST_URL || "http://192.168.10.27:3010/#focal-bi",
  );
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
  assert.ok(frame, "native SDK embedded route");
  await frame
    .getByText("FDS Solutions Limited awarded value (HKD)", { exact: true })
    .waitFor({ timeout: 120000 });
  await frame
    .getByText("72,002,518.80", { exact: true })
    .waitFor({ timeout: 60000 });
  await frame.waitForFunction(
    `document.querySelectorAll('[data-test="focalbi-chart"] canvas').length===4`,
    { timeout: 60000 },
  );
  await page.waitForTimeout(1800);
  const baseline = await frame.evaluate(inspect);
  assert.equal(baseline.charts.length, 8);
  assert.equal(
    await frame.locator('[data-test="focalbi-native-fallback"]').count(),
    0,
  );
  const company = baseline.filters.find(
    (filter: { name: string }) => filter.name === "Company",
  );
  const annual = baseline.charts.find(
    (chart: { type: string }) => chart.type === "mixed_timeseries",
  );
  const rank = baseline.charts.find(
    (chart: { type: string }) => chart.type === "echarts_timeseries_bar",
  );
  assert.equal(annual.series[0].data.length, 5);
  assert.deepEqual(
    annual.series.map((series: { type: string }) => series.type),
    ["bar", "line"],
  );
  assert.ok(
    !annual.series[1].areaStyle ||
      Object.keys(annual.series[1].areaStyle).length === 0 ||
      annual.series[1].areaStyle.opacity === 0,
    "annual share line has no area fill",
  );
  assert.ok(annual.series[1].z >= annual.series[0].z);
  assert.equal(rank.series[0].data.length, 10);
  const ascendingValues = rank.series[0].data.map(
    (point: { value: number[] }) => point.value[0],
  );
  assert.deepEqual(
    ascendingValues,
    [...ascendingValues].sort((a: number, b: number) => a - b),
  );
  await frame.getByText("Value: lowest first", { exact: true }).click();
  await frame.waitForFunction(
    `(() => {const state=${inspect};const rank=state.charts.find(c=>c.type==='echarts_timeseries_bar');const data=rank.series[0].data;return data[0].value[0]>data[data.length-1].value[0]})()`,
    null,
    { timeout: 60000 },
  );
  await frame.getByText("Value: highest first", { exact: true }).click();
  await frame.waitForFunction(
    `(() => {const state=${inspect};const rank=state.charts.find(c=>c.type==='echarts_timeseries_bar');const data=rank.series[0].data;return data[0].value[0]<data[data.length-1].value[0]})()`,
    null,
    { timeout: 60000 },
  );
  assert.equal(
    rank.series[0].data.find(
      (d: { value: unknown[] }) => d.value[1] === "FDS Solutions Limited",
    ).itemStyle.color,
    "#66B3E1",
  );
  const companyInput = frame.getByRole("combobox", {
    name: company.id,
    exact: true,
  });
  await companyInput.click();
  await companyInput.fill("OPM");
  await frame
    .locator(".ant-select-item-option-content")
    .getByText("OPM Systems Company Limited", { exact: true })
    .click();
  await companyInput.press("Escape");
  // Draft selections must not change titles or results before native Apply.
  assert.ok(
    await frame
      .getByText("FDS Solutions Limited awarded value (HKD)", { exact: true })
      .count(),
  );
  await frame
    .getByRole("button", { name: "Apply filters", exact: true })
    .click();
  await frame
    .getByText("183,079,390.79", { exact: true })
    .waitFor({ timeout: 120000 });
  await frame.getByText("150", { exact: true }).waitFor({ timeout: 60000 });
  await frame.waitForFunction(
    `(() => {const state=${inspect};const annual=state.charts.find(c=>c.type==='mixed_timeseries');const table=state.charts.find(c=>c.type==='table');return state.charts.every(c=>c.status==='rendered') && table.rows[0].length===150 && Math.abs(annual.rows[0].reduce((sum,row)=>sum+row['Award value (HKD)'],0)-183079390.79)<0.01})()`,
    null,
    { timeout: 120000 },
  );
  await page.waitForTimeout(1800);
  const multi = await frame.evaluate(inspect);
  const kpis = multi.charts.filter(
    (chart: { type: string }) => chart.type === "big_number_total",
  );
  assert.deepEqual(
    kpis.map(
      (chart: { rows: Record<string, number>[][] }) =>
        Object.values(chart.rows[0][0])[0],
    ),
    [183079390.79, 150, 52],
  );
  assert.equal(kpis[0].title, "Awarded value (HKD)");
  const pie = multi.charts.find((chart: { name: string }) =>
    chart.name.includes("and peers"),
  );
  const selected = pie.series[0].data.filter(
    (d: { name: string }) => d.name !== "Other contractors",
  );
  assert.equal(selected.length, 2);
  assert.notEqual(selected[0].itemStyle.color, selected[1].itemStyle.color);
  const total = pie.series[0].data.reduce(
    (sum: number, d: { value: number }) => sum + d.value,
    0,
  );
  const numerator = selected.reduce(
    (sum: number, d: { value: number }) => sum + d.value,
    0,
  );
  assert.ok(Math.abs(numerator / total - 0.198915) < 0.0001);
  const multiRank = multi.charts.find(
    (chart: { type: string }) => chart.type === "echarts_timeseries_bar",
  );
  for (const datum of selected) {
    assert.equal(
      multiRank.series[0].data.find(
        (d: { value: unknown[] }) => d.value[1] === datum.name,
      ).itemStyle.color,
      datum.itemStyle.color,
    );
  }
  assert.deepEqual(
    multiRank.rows,
    rank.rows,
    "company selection does not restrict ranking population",
  );
  await frame.locator("body").screenshot({
    path: resolve(root, "test-results/native-company-multi.png"),
  });

  await frame.evaluate(
    `(() => {const node=[...document.querySelectorAll('[data-test="chart-grid-component"]')].find(node=>node.getAttribute('data-test-chart-name')?.includes('and peers'));const plot=node.querySelector('[_echarts_instance_]');let f=plot[Object.keys(plot).find(k=>k.startsWith('__reactFiber'))];while(f){let h=f.memoizedState;while(h){const instance=h.memoizedState?.current;if(instance?.getOption && instance?.dispatchAction){instance.dispatchAction({type:'legendUnSelect',name:'Other contractors'});return}h=h.next}f=f.return}throw new Error('Missing chart instance')})()`,
  );
  await page.waitForTimeout(500);
  const interactive = await frame.evaluate(inspect);
  assert.equal(
    interactive.charts.find((c: { name: string }) =>
      c.name.includes("and peers"),
    ).legend[0].selected["Other contractors"],
    false,
    "native legend interaction was applied before switching",
  );

  // Native sorting and paging persist across engine component replacement.
  const table = frame.locator(
    '[data-test="chart-grid-component"][data-test-viz-type="table"]',
  );
  await table.getByText("Award Date", { exact: true }).click();
  await table.locator(".pagination").getByText("2", { exact: true }).click();
  const tableBefore = await table.locator("tbody").innerText();
  const beforeQueries = queries;
  const switchTo = async (name: string) => {
    await frame
      .locator('[data-test="focalbi-renderer-toolbar"] .ant-select-selector')
      .click();
    await frame
      .locator(".ant-select-item-option-content")
      .getByText(name, { exact: true })
      .click();
    await page.waitForTimeout(1800);
  };
  await switchTo("Superset baseline");
  assert.equal(await table.locator("tbody").innerText(), tableBefore);
  const switched = await frame.evaluate(inspect);
  assert.deepEqual(
    switched.charts.map((c: { rows: unknown }) => c.rows),
    multi.charts.map((c: { rows: unknown }) => c.rows),
  );
  assert.deepEqual(
    switched.charts.map((c: { series: unknown }) => c.series),
    interactive.charts.map((c: { series: unknown }) => c.series),
  );
  assert.equal(
    switched.charts.find((c: { name: string }) => c.name.includes("and peers"))
      .legend[0].selected["Other contractors"],
    false,
  );
  assert.equal(queries, beforeQueries, "switch does not requery");
  await switchTo("FocalBI fork");
  assert.equal(await table.locator("tbody").innerText(), tableBefore);
  assert.equal(queries, beforeQueries);
  const year = baseline.filters.find(
    (filter: { name: string }) => filter.name === "Award year",
  );
  await frame.getByRole("combobox", { name: year.id, exact: true }).click();
  await frame
    .locator(".ant-select-item-option-content")
    .getByText("2025", { exact: true })
    .click();
  await frame
    .getByRole("combobox", { name: year.id, exact: true })
    .press("Escape");
  await frame
    .getByRole("button", { name: "Apply filters", exact: true })
    .click();
  await frame.waitForFunction(
    `(() => {const state=${inspect};const table=state.charts.find(c=>c.type==='table');return table.status==='rendered' && table.rows[0].length>0 && table.rows[0].every(row=>new Date(row.award_date).getUTCFullYear()===2025)})()`,
    null,
    { timeout: 120000 },
  );
  const scoped = await frame.evaluate(inspect);
  assert.deepEqual(
    scoped.charts.find((c: { type: string }) => c.type === "mixed_timeseries")
      .rows,
    multi.charts.find((c: { type: string }) => c.type === "mixed_timeseries")
      .rows,
    "annual timeline excludes year filter",
  );
  assert.ok(
    scoped.charts
      .find((c: { type: string }) => c.type === "echarts_timeseries_bar")
      .filters.some((f: { col: string }) => f.col === "award_year"),
  );
  assert.ok(
    scoped.charts
      .find((c: { type: string }) => c.type === "table")
      .rows[0].every(
        (row: { award_date: number }) =>
          new Date(row.award_date).getUTCFullYear() === 2025,
      ),
  );
  const companyControl = frame
    .locator(".ant-select")
    .filter({ has: companyInput });
  assert.equal(await companyControl.count(), 1);
  await companyControl.hover();
  await companyControl.locator(".ant-select-clear").click();
  assert.ok(
    await frame
      .getByRole("button", { name: "Apply filters", exact: true })
      .isDisabled(),
    "required empty company selection prevents Apply",
  );
  assert.deepEqual(
    (await frame.evaluate(inspect)).charts.map(
      (c: { rows: unknown }) => c.rows,
    ),
    scoped.charts.map((c: { rows: unknown }) => c.rows),
    "empty draft retains applied data",
  );
  assert.deepEqual(errors, []);
  writeFileSync(
    resolve(root, "test-results/native-browser.json"),
    JSON.stringify(
      {
        passed: true,
        chartCount: 8,
        queries,
        single: baseline.charts
          .filter((c: { type: string }) => c.type === "big_number_total")
          .map((c: { rows: unknown }) => c.rows),
        multi: {
          value: numerator,
          share: numerator / total,
          colors: selected.map((d: { name: string; itemStyle: unknown }) => ({
            name: d.name,
            style: d.itemStyle,
          })),
        },
        checks: [
          "native routes",
          "applied titles",
          "company multiselect",
          "KPI reconciliation",
          "distinct department relationships",
          "eligible market denominator",
          "consistent highlights",
          "annual bars and unfilled share line",
          "renderer parity",
          "switch without queries",
          "sort and pagination preserved",
          "legend preserved",
          "required empty selection",
          "native year scopes",
          "formal dates",
          "native bar value-sort controls",
        ],
        errors,
      },
      null,
      2,
    ),
  );
  console.log("Native browser acceptance checks passed.");
} finally {
  await browser.close();
}
