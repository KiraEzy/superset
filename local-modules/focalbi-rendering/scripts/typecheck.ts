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
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { mkdirSync, writeFileSync } from "node:fs";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const upstream = resolve(root, "../../superset-frontend");
const require = createRequire(resolve(upstream, "package.json"));
const ts = require("typescript");
const config = ts.readConfigFile(
  resolve(upstream, "tsconfig.json"),
  ts.sys.readFile,
).config;
const options = ts.parseJsonConfigFileContent(config, ts.sys, upstream).options;
Object.assign(options, {
  noEmit: true,
  composite: false,
  noUnusedLocals: false,
  rootDir: undefined,
  strict: true,
  typeRoots: [resolve(upstream, "node_modules/@types")],
});
Object.assign(options.paths, {
  "focalbi-native/DashboardBuilder": [
    "src/dashboard/components/DashboardBuilder/DashboardBuilder.tsx",
  ],
  "focalbi-native/SliceHeader": [
    "src/dashboard/components/SliceHeader/index.tsx",
  ],
  "focalbi-native/SuperChartCore": [
    "packages/superset-ui-core/src/chart/components/SuperChartCore.tsx",
  ],
  "focalbi-native/DataTable": [
    "plugins/plugin-chart-table/src/DataTable/index.tsx",
  ],
  "*": [
    resolve(upstream, "node_modules/*"),
    resolve(upstream, "node_modules/@types/*"),
    resolve(upstream, "*"),
  ],
});
const files = [
  "DeckGL.tsx",
  "DashboardBuilder.tsx",
  "SuperChartCore.tsx",
  "SliceHeader.tsx",
  "DataTable.tsx",
  "registry.tsx",
];
const program = ts.createProgram(
  files.map((name) => resolve(root, "frontend", name)),
  options,
);
const diagnostics = ts.getPreEmitDiagnostics(program);
const owned = diagnostics.filter(
  (item: { file?: { fileName: string } }) =>
    !item.file || item.file.fileName.startsWith(resolve(root, "frontend")),
);
const host = {
  getCurrentDirectory: () => root,
  getCanonicalFileName: (name: string) => name,
  getNewLine: () => "\n",
};
mkdirSync(resolve(root, "test-results"), { recursive: true });
writeFileSync(
  resolve(root, "test-results/native-type-diagnostics.txt"),
  ts.formatDiagnostics(
    diagnostics.filter((item: object) => !owned.includes(item)),
    host,
  ),
);
console.log(
  ts.formatDiagnosticsWithColorAndContext(owned, host) ||
    "Module presentation type checks passed.",
);
console.log(
  `${diagnostics.length - owned.length} upstream diagnostics recorded separately.`,
);
if (owned.length) process.exitCode = 1;
