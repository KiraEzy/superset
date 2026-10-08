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
import { fileURLToPath, pathToFileURL } from "node:url";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(
  resolve(root, "../../superset-frontend/package.json"),
);
const ts = require("typescript");
const output = resolve(root, ".runtime/frontend-tests");
mkdirSync(output, { recursive: true });
for (const name of [
  "contracts",
  "presentation",
  "embedding",
  "displayState",
  "tableState",
  "controls",
  "filterActions",
]) {
  const source = readFileSync(resolve(root, `frontend/${name}.ts`), "utf8");
  writeFileSync(
    resolve(output, `${name}.js`),
    ts
      .transpileModule(source, {
        compilerOptions: {
          module: ts.ModuleKind.ESNext,
          target: ts.ScriptTarget.ES2020,
        },
      })
      .outputText.replaceAll('"./contracts"', '"./contracts.js"')
      .replaceAll('"./controls"', '"./controls.js"'),
  );
}
const contracts = await import(
  pathToFileURL(resolve(output, "contracts.js")).href
);
const { localizeProps } = await import(
  pathToFileURL(resolve(output, "presentation.js")).href
);
const { controlMessage, localizeTotal } = await import(
  pathToFileURL(resolve(output, "controls.js")).href
);
const { filterActionValues } = await import(
  pathToFileURL(resolve(output, "filterActions.js")).href
);
test("Dropdown bulk selection preserves raw identities, disabled values and existing selections", () => {
  const options = [
    { value: 0, label: "Zero" },
    { value: false, label: "False" },
    { value: "", label: "Empty" },
    { value: null, label: "Null" },
    { value: "0", label: "Zero text" },
    { value: "locked", disabled: true },
    { value: "invented", isNewOption: true },
    { value: undefined },
    { value: 0, label: "Duplicate zero" },
  ];
  const selected = ["previous", "locked"];
  const result = filterActionValues(options, selected, "");
  assert.deepEqual(result.all, ["previous", "locked", 0, false, "", null, "0"]);
  assert.deepEqual(selected, ["previous", "locked"]);
  assert.equal(filterActionValues(options, result.all, "").additions.length, 0);
});
test("Dropdown search matches translated labels or raw values without clearing other selections", () => {
  const options = [
    { value: "North", label: "北區" },
    { value: "South", label: "南區" },
    { value: "North-2", label: "北區" },
  ];
  assert.deepEqual(filterActionValues(options, ["South"], "北區").all, [
    "South",
    "North",
    "North-2",
  ]);
  assert.deepEqual(filterActionValues(options, [], "  nOrTh ").additions, [
    "North",
    "North-2",
  ]);
  assert.deepEqual(filterActionValues(options, ["South"], "no match").all, [
    "South",
  ]);
  assert.deepEqual(filterActionValues([], null, "").all, []);
});
test("Dropdown action labels cover all supported viewer locales", () => {
  for (const [locale, select, clear] of [
    ["en", "Select all", "Clear"],
    ["zh-Hant", "全選", "清除"],
    ["zh-Hans", "全选", "清除"],
  ]) {
    assert.equal(controlMessage(locale, "filter.selectAll"), select);
    assert.equal(controlMessage(locale, "filter.clearSelection"), clear);
  }
});
test("Viewer control dictionaries preserve native totals and cover zero/one/many without shared locale state", () => {
  assert.equal(
    controlMessage("zh-Hant", "filter.options", { count: 5 }),
    "5 個選項",
  );
  assert.equal(
    controlMessage("zh-Hans", "table.records", { count: 0 }),
    "0 条记录…",
  );
  assert.equal(controlMessage("en", "filter.option", { count: 1 }), "1 option");
  assert.equal(localizeTotal("zh-Hant", "Total: HK$72.00M"), "總計：HK$72.00M");
  assert.equal(
    localizeTotal("zh-Hans", "Somme (53)", "Somme ({value})"),
    "总计：53",
  );
  assert.equal(
    localizeTotal("zh-Hant", "Custom total title"),
    "Custom total title",
  );
  assert.equal(controlMessage("en", "filter.heading"), "Filters and controls");
});
test("Legend control titles keep native action identities, custom labels, disabled controls and formatting", () => {
  const raw = {
    echartOptions: {
      legend: [
        {
          selector: ["all", "inverse", { type: "all", title: "Custom" }],
          selected: { North: false },
        },
        { selector: false },
      ],
      graphic: { type: "text", style: { text: "Total: 53" } },
      series: [],
    },
  };
  const localized = localizeProps("pie", raw, {
    dimensions: [],
    locale: "zh-Hant",
  });
  assert.deepEqual(localized.echartOptions.legend[0].selector, [
    { type: "all", title: "全選" },
    { type: "inverse", title: "反選" },
    { type: "all", title: "Custom" },
  ]);
  assert.equal(
    localized.echartOptions.legend[0].selected,
    raw.echartOptions.legend[0].selected,
  );
  assert.equal(localized.echartOptions.legend[1].selector, false);
  assert.equal(localized.echartOptions.graphic[0].style.text, "總計：53");
  assert.equal(raw.echartOptions.graphic.style.text, "Total: 53");
});
const { needsDisplayRestore, retainDisplayProps, sameResultData } =
  await import(pathToFileURL(resolve(output, "displayState.js")).href);
test("Remembered legend and zoom reach both engines before drawing without changing series or source options", () => {
  const series = [{ name: "North", data: [1, 2] }];
  const raw = {
    echartOptions: {
      series,
      legend: { show: true, selected: {} },
      dataZoom: [{ type: "slider", start: 0, end: 100 }],
    },
  };
  const result = retainDisplayProps(raw, {
    legends: [{ selected: { North: false } }],
    zoom: [{ start: 20, end: 80 }],
  });
  assert.equal(result.echartOptions.series, series);
  assert.deepEqual(result.echartOptions.legend, {
    show: true,
    selected: { North: false },
  });
  assert.deepEqual(result.echartOptions.dataZoom, [
    { type: "slider", start: 20, end: 80 },
  ]);
  assert.deepEqual(raw.echartOptions.legend.selected, {});
  assert.equal(raw.echartOptions.dataZoom[0].start, 0);
  assert.equal(retainDisplayProps({ data: [1] }, {}).data[0], 1);
});
test("Repackaged native JSON keeps interaction identity; changed raw records reset it", () => {
  const original = [[{ region_code: "North", amount_total: 0 }]];
  assert.equal(
    sameResultData(original, JSON.parse(JSON.stringify(original))),
    true,
  );
  assert.equal(
    sameResultData(original, [[{ region_code: "North", amount_total: null }]]),
    false,
  );
  assert.equal(
    sameResultData(original, [[{ region_code: "South", amount_total: 0 }]]),
    false,
  );
  assert.equal(sameResultData(original, []), false);
});
const { TableDisplayState } = await import(
  pathToFileURL(resolve(output, "tableState.js")).href
);

test("Table presentation changes retain state; new queries, removed columns and user sorting reset natively", () => {
  const saved = new TableDisplayState();
  const query = {};
  const initial = {};
  const locale = {};
  const previous = {
    pageIndex: 2,
    sortBy: [{ id: "event_on", desc: false }],
    globalFilter: "North",
  };
  const reset = { pageIndex: 0, sortBy: [], globalFilter: "" };
  saved.update(initial, query, "event_on,region_code");
  saved.update(locale, query, "event_on,region_code");
  assert.deepEqual(
    saved.reduce(reset, previous, { type: "resetPage" }),
    previous,
  );
  assert.deepEqual(
    saved.reduce(reset, previous, { type: "resetSortBy" }),
    previous,
  );
  saved.reduce(reset, previous, { type: "toggleSortBy" });
  assert.deepEqual(saved.reduce(reset, previous, { type: "resetPage" }), reset);
  saved.update({}, query, "event_on,region_code");
  saved.update({}, {}, "event_on,region_code");
  assert.deepEqual(saved.reduce(reset, previous, { type: "resetPage" }), reset);
  saved.update({}, query, "event_on,region_code");
  saved.update({}, query, "event_on");
  assert.deepEqual(
    saved.reduce(reset, previous, { type: "resetSortBy" }),
    reset,
  );
});
test("Zoom and raw legend identities restore after a display redraw without recursion", () => {
  const saved = {
    zoom: [{ start: 20, end: 80 }],
    legends: [{ selected: { North: false, South: true }, scrollDataIndex: 1 }],
  };
  assert.equal(
    needsDisplayRestore(
      {
        dataZoom: [{ start: 0, end: 100 }],
        legend: [
          { selected: { North: true, South: true }, scrollDataIndex: 1 },
        ],
      },
      saved,
    ),
    true,
  );
  assert.equal(
    needsDisplayRestore({ dataZoom: saved.zoom, legend: saved.legends }, saved),
    false,
  );
  assert.equal(needsDisplayRestore({}, {}), false);
  assert.deepEqual(Object.keys(saved.legends[0].selected), ["North", "South"]);
});
const dataset = {
  uuid: "unrelated-dataset",
  fields: [
    {
      key: "column/uuid/label",
      kind: "text",
      target: "region_code",
      source: "Region",
    },
    {
      key: "column/uuid/categories",
      kind: "category",
      target: "region_code",
      source: "region_code",
    },
  ],
  translations: {
    "column/uuid/label": { text: "地區" },
    "column/uuid/categories": {
      dictionary: [
        { value: "N", label: "地區" },
        { value: "S", label: "地區" },
      ],
    },
  },
};
const chart = {
  uuid: "unrelated-chart",
  fields: [
    {
      key: "column/region_code",
      target: "region_code",
      source: "Original custom label",
    },
  ],
  translations: { "column/region_code": { text: "地區" } },
};
const context = { chart, dataset, dimensions: ["region_code"] };
test("Locale URL and embedded isolation precedence", () => {
  assert.equal(
    contracts.initialLocale(
      new URL("http://example/dashboard?content_locale=zh-Hant"),
      false,
      "zh-Hans",
      "en",
    ),
    "zh-Hant",
  );
  assert.equal(
    contracts.initialLocale(
      new URL("http://example/embedded/test"),
      true,
      "zh-Hant",
      "en",
    ),
    "en",
  );
  assert.equal(contracts.normalizeLocale("zh_TW"), "zh-Hant");
  assert.equal(contracts.normalizeLocale("zh-CN"), "zh-Hans");
});
test("Table headers and categories translate without changing row or sort keys", () => {
  const data = [{ region_code: "N", amount_total: 1000 }];
  const raw = {
    data,
    columns: [
      {
        key: "region_code",
        label: "Region",
        config: { customColumnName: "Original custom label" },
      },
      {
        key: "amount_total",
        label: "Amount",
        formatter: (value: number) => value.toFixed(2),
      },
    ],
  };
  const result = localizeProps("table", raw, context);
  assert.equal(result.data, data);
  assert.equal(result.columns[0].key, "region_code");
  assert.equal(result.columns[0].label, "地區");
  assert.equal(result.columns[0].config.customColumnName, "地區");
  assert.equal(result.columns[0].formatter("N"), "地區");
  assert.equal(result.columns[0].formatter("S"), "地區");
  assert.equal(result.columns[1].formatter(1000), "1000.00");
});
test("Series identities, colors, area layering and formatter callback inputs survive", () => {
  const value = { name: "N", value: 100, percent: 7.82 };
  const options = {
    series: [
      {
        name: "total_amount",
        data: [value],
        z: 2,
        itemStyle: { color: "blue" },
        areaStyle: { opacity: 0.3 },
        label: { formatter: "{b}: {d}%" },
      },
    ],
    legend: { data: ["N", "S"] },
    yAxis: { axisLabel: { formatter: (value: number) => value.toFixed(1) } },
  };
  const result = localizeProps(
    "pie",
    { echartOptions: options },
    context,
  ).echartOptions;
  assert.equal(result.series[0].name, "total_amount");
  assert.equal(result.series[0].data, options.series[0].data);
  assert.equal(result.series[0].itemStyle, options.series[0].itemStyle);
  assert.equal(result.series[0].z, 2);
  assert.equal(result.series[0].label.formatter(value), "地區: 7.82%");
  assert.equal(result.legend[0].formatter("N"), "地區");
  assert.equal(result.legend[0].formatter("S"), "地區");
  assert.equal(result.yAxis[0].axisLabel.formatter(1000, 0), "1000.0");
});
test("Tooltip translations are escaped and never alter HTML attributes or raw params", () => {
  const unsafe = {
    ...dataset,
    translations: {
      "column/uuid/categories": {
        dictionary: [{ value: "N", label: "<script>bad</script>" }],
      },
    },
  };
  let seen;
  const raw = {
    echartOptions: {
      series: [],
      tooltip: {
        formatter: (params: object) => {
          seen = params;
          return '<div data-key="N">N</div>';
        },
      },
    },
  };
  const result = localizeProps("pie", raw, {
    dataset: unsafe,
    dimensions: ["region_code"],
  });
  const params = { name: "N" };
  assert.equal(
    result.echartOptions.tooltip.formatter(params),
    '<div data-key="N">&lt;script&gt;bad&lt;/script&gt;</div>',
  );
  assert.equal(seen, params);
});
test("Unsupported renderers retain native props and missing categories retain original", () => {
  const raw = { native: true };
  assert.equal(localizeProps("unregistered-viz", raw, context), raw);
  assert.equal(contracts.category(dataset, "region_code", "Z"), undefined);
});

test("Horizontal axes follow native swapped controls and native legend formatting survives fallback", () => {
  const chart = {
    fields: [
      { key: "control/x_axis_title", source: "Region axis" },
      { key: "control/y_axis_title", source: "Amount axis" },
    ],
    translations: {
      "control/x_axis_title": { text: "地區軸" },
      "control/y_axis_title": { text: "金額軸" },
    },
  };
  let seen;
  const raw = {
    echartOptions: {
      xAxis: { name: "Amount axis" },
      yAxis: { name: "Region axis" },
      legend: {
        formatter: (name: string) => {
          seen = name;
          return `[${name}]`;
        },
      },
    },
  };
  const result = localizeProps("echarts_timeseries_bar", raw, {
    chart,
    dimensions: [],
    sourceControls: {
      orientation: "horizontal",
      x_axis_title: "Region axis",
      y_axis_title: "Amount axis",
    },
  }).echartOptions;
  assert.equal(result.xAxis[0].name, "金額軸");
  assert.equal(result.yAxis[0].name, "地區軸");
  assert.equal(result.legend[0].formatter("Unmapped"), "[Unmapped]");
  assert.equal(seen, "Unmapped");
});
test("Unsaved native labels and controls supersede an older catalog", () => {
  const changed = localizeProps(
    "table",
    {
      columns: [
        {
          key: "region_code",
          label: "Region",
          config: { customColumnName: "New unsaved name" },
        },
      ],
    },
    context,
  );
  assert.equal(changed.columns[0].config.customColumnName, "New unsaved name");
  const metadata = {
    uuid: "chart",
    fields: [{ key: "control/y_axis_title", source: "Amount" }],
    translations: { "control/y_axis_title": { text: "金額" } },
  };
  const raw = {
    echartOptions: { series: [], yAxis: { name: "New native title" } },
  };
  const result = localizeProps("mixed_timeseries", raw, {
    chart: metadata,
    sourceControls: { y_axis_title: "New native title" },
    dimensions: [],
  });
  assert.equal(result.echartOptions.yAxis[0].name, "New native title");
});
test("Bridge queues latest locale and rejects wrong origin, source, version and stale acknowledgement", async () => {
  let listener: ((event: object) => void) | undefined;
  let probe: (() => void) | undefined;
  const messages: object[] = [];
  const target = {
    postMessage: (message: object, origin: string) =>
      messages.push({ message, origin }),
  };
  const fakeWindow = {
    location: { href: "https://website.test/page" },
    addEventListener: (_: string, callback: (event: object) => void) => {
      listener = callback;
    },
    removeEventListener: () => {
      listener = undefined;
    },
    setInterval: (callback: () => void) => {
      probe = callback;
      return 1;
    },
  };
  Object.defineProperty(globalThis, "window", {
    value: fakeWindow,
    configurable: true,
  });
  const { createLocaleBridge } = await import(
    pathToFileURL(resolve(output, "embedding.js")).href
  );
  const applied: string[] = [];
  const bridge = createLocaleBridge(
    { src: "https://bi.test/embedded/uuid", contentWindow: target },
    "en",
    (locale: string) => applied.push(locale),
  );
  bridge.setContentLocale("zh-Hant");
  bridge.setContentLocale("zh-Hans");
  assert.equal(messages.length, 0);
  const message = { type: contracts.bridgeType, version: 1, action: "ready" };
  listener!({ source: target, origin: "https://wrong.test", data: message });
  listener!({ source: {}, origin: "https://bi.test", data: message });
  listener!({
    source: target,
    origin: "https://bi.test",
    data: { ...message, version: 2 },
  });
  assert.equal(messages.length, 0);
  probe!();
  assert.equal(messages.length, 1);
  listener!({ source: target, origin: "https://bi.test", data: message });
  assert.equal(messages.length, 2);
  assert.equal(
    (messages[1] as { message: { locale: string } }).message.locale,
    "zh-Hans",
  );
  listener!({
    source: target,
    origin: "https://bi.test",
    data: { ...message, action: "ack", requestId: 0 },
  });
  assert.deepEqual(applied, []);
  listener!({
    source: target,
    origin: "https://bi.test",
    data: { ...message, action: "ack", requestId: 1, locale: "zh-Hans" },
  });
  assert.deepEqual(applied, ["zh-Hans"]);
  bridge.destroy();
  assert.equal(listener, undefined);
  Reflect.deleteProperty(globalThis, "window");
});
