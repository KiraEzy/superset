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
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(
  resolve(root, "../../superset-frontend/package.json"),
);
const ts = require("typescript");
const loader = require(resolve(root, "scripts/source-loader.cts"));
const upstream = resolve(root, "../../superset-frontend");
const renderer = resolve(root, "../focalbi-rendering");
const sources = [
  resolve(
    upstream,
    "src/dashboard/components/nativeFilters/FilterBar/Header/index.tsx",
  ),
  resolve(
    upstream,
    "src/dashboard/components/nativeFilters/FilterBar/ActionButtons/index.tsx",
  ),
  resolve(upstream, "src/filters/components/Select/SelectFilterPlugin.tsx"),
  resolve(
    upstream,
    "plugins/plugin-chart-echarts/src/Timeseries/EchartsTimeseries.tsx",
  ),
  resolve(upstream, "plugins/plugin-chart-table/src/DataTable/DataTable.tsx"),
  resolve(upstream, "plugins/plugin-chart-table/src/TableChart.tsx"),
  resolve(renderer, "frontend/DashboardBuilder.tsx"),
  ...["baseline", "fork"].flatMap((engine) => [
    resolve(
      renderer,
      `vendor/${engine}/echarts/Timeseries/EchartsTimeseries.tsx`,
    ),
    resolve(renderer, `vendor/${engine}/table/DataTable/DataTable.tsx`),
    resolve(renderer, `vendor/${engine}/table/TableChart.tsx`),
  ]),
];
for (const resourcePath of sources) {
  const before = readFileSync(resourcePath, "utf8");
  const context = {
    resourcePath,
    getOptions: () => ({ hooks: resolve(root, "frontend/hooks.ts") }),
  };
  const compiled = loader.call(context, before);
  assert.notEqual(compiled, before);
  if (resourcePath.endsWith("SelectFilterPlugin.tsx")) {
    assert.ok(
      compiled.includes("multiSelect ? {"),
      "Single-select popup remains native",
    );
    assert.ok(compiled.includes("<FilterDropdown options={options}"));
    assert.ok(
      compiled.includes("handleChange(values as SelectValue)"),
      "Native filter callback remains authoritative",
    );
    assert.ok(compiled.includes("disabled={isDisabled || isRefreshing}"));
    assert.ok(
      compiled.includes("onSearch={onSearch}"),
      "Native debounced search callback is unchanged",
    );
    assert.ok(compiled.includes("onBlur={handleBlur}"));
    assert.ok(compiled.includes("onClear={() => onSearch('')}"));
    for (const start of [
      "  const updateDataMask = useCallback(",
      "function reducer(",
    ]) {
      const end = start.startsWith("function")
        ? "const StyledSpace"
        : "  const isDisabled";
      assert.equal(
        compiled.slice(compiled.indexOf(start), compiled.indexOf(end)),
        before
          .slice(before.indexOf(start), before.indexOf(end))
          .replaceAll("\r\n", "\n"),
        "Native data-mask/reducer code remains unchanged apart from loader newline normalization",
      );
    }
  }
  const diagnostics =
    ts.transpileModule(compiled, {
      fileName: resourcePath,
      reportDiagnostics: true,
      compilerOptions: {
        jsx: ts.JsxEmit.React,
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2020,
      },
    }).diagnostics || [];
  assert.equal(
    diagnostics.filter(
      (item: { category: number }) =>
        item.category === ts.DiagnosticCategory.Error,
    ).length,
    0,
    resourcePath,
  );
  assert.equal(
    readFileSync(resourcePath, "utf8"),
    before,
    "Native/snapshot source remains intact",
  );
  assert.throws(
    () => loader.call(context, "// incompatible upstream component"),
    /compatibility check failed/,
  );
}
console.log(
  `Display overlay compatibility and TSX syntax passed (${sources.length} source surfaces); native files untouched.`,
);
