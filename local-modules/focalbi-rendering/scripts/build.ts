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
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { verifyDependencies } from "./dependency-provenance.ts";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const upstream = resolve(root, "../../superset-frontend");
const require = createRequire(resolve(upstream, "package.json"));
process.chdir(upstream);
process.env.NODE_ENV = "production";
process.argv.push("--mode=production");
execFileSync("python", [resolve(root, "scripts/snapshot.py"), "--verify"], {
  stdio: "inherit",
});
const webpack = require("webpack");
const config = require(resolve(upstream, "webpack.config.js"));
const nativePaths: Record<string, string> = {
  DashboardBuilder:
    "src/dashboard/components/DashboardBuilder/DashboardBuilder.tsx",
  SliceHeader: "src/dashboard/components/SliceHeader/index.tsx",
  SuperChartCore:
    "packages/superset-ui-core/src/chart/components/SuperChartCore.tsx",
  DataTable: "plugins/plugin-chart-table/src/DataTable/index.tsx",
};
for (const [name, path] of Object.entries(nativePaths))
  config.resolve.alias[`focalbi-native/${name}$`] = resolve(upstream, path);
config.resolve.modules.push(
  resolve(root, "node_modules"),
  resolve(upstream, "node_modules"),
);
config.resolveLoader = { modules: [resolve(upstream, "node_modules")] };
config.output.path = resolve(root, "dist/assets");
config.output.clean = false;
config.cache = {
  type: "filesystem",
  cacheDirectory: resolve(root, ".build/native-webpack"),
  buildDependencies: { config: [fileURLToPath(import.meta.url)] },
};
// Minification is disabled to avoid parallel minifier workers on developer hosts.
config.optimization.minimize = false;
config.devtool = false;
config.module.rules
  .filter((rule: { test?: RegExp; include?: unknown }) =>
    rule.test?.test("module.css"),
  )
  .forEach((rule: { include: unknown[] }) => {
    rule.include = [...rule.include, root];
  });
config.plugins = config.plugins.filter(
  (plugin: { constructor: { name: string } }) =>
    !["BundleAnalyzerPlugin", "VisualizerPlugin"].includes(
      plugin.constructor.name,
    ),
);
config.plugins.push(
  new webpack.NormalModuleReplacementPlugin(
    /DashboardBuilder|SliceHeader|SuperChartCore|setupPluginsExtra|DataTable$/,
    (resource: { request: string; context: string }) => {
      if (resource.request.startsWith("focalbi-native/")) return;
      let replacement: string | undefined;
      if (
        resource.request ===
        "src/dashboard/components/DashboardBuilder/DashboardBuilder"
      )
        replacement = "DashboardBuilder";
      else if (
        resource.request === "src/dashboard/components/SliceHeader" ||
        resolve(resource.context, resource.request) ===
          resolve(upstream, "src/dashboard/components/SliceHeader")
      )
        replacement = "SliceHeader";
      else if (resource.request === "./SuperChartCore")
        replacement = "SuperChartCore";
      else if (
        resource.request.endsWith("/setupPluginsExtra") ||
        resource.request === "./setupPluginsExtra"
      )
        replacement = "setupPluginsExtra";
      else if (
        resource.request === "./DataTable" &&
        /[\\/](table|plugin-chart-table[\\/]src)$/.test(resource.context)
      )
        replacement = "DataTable";
      if (replacement)
        resource.request = resolve(root, `frontend/${replacement}.tsx`);
      if (replacement === "setupPluginsExtra")
        resource.request = resolve(root, "frontend/setupPluginsExtra.ts");
    },
  ),
);
const protectedFiles = [
  "src/hooks/apiResources/dashboards.ts",
  "src/dashboard/containers/DashboardPage.tsx",
  "src/dashboard/util/charts/getFormDataWithExtraFilters.ts",
  "src/explore/exploreUtils/index.ts",
  "src/components/Chart/chartAction.ts",
  "plugins/plugin-chart-echarts/src/BigNumber/BigNumberTotal/buildQuery.ts",
  "plugins/plugin-chart-echarts/src/Pie/buildQuery.ts",
  "plugins/plugin-chart-echarts/src/Timeseries/buildQuery.ts",
  "plugins/plugin-chart-echarts/src/MixedTimeseries/buildQuery.ts",
  "plugins/plugin-chart-table/src/buildQuery.ts",
  ...Object.values(nativePaths),
];
const sha256 = (path: string) =>
  createHash("sha256")
    .update(readFileSync(resolve(upstream, path)))
    .digest("hex");
const before = Object.fromEntries(
  protectedFiles.map((path) => [path, sha256(path)]),
);
await new Promise<void>((complete, reject) =>
  webpack(
    config,
    (
      error: Error | null,
      stats: {
        hasErrors(): boolean;
        toString(options: object): string;
        toJson(options: object): {
          modules: Parameters<typeof verifyDependencies>[2];
        };
      },
    ) => {
      if (error || stats?.hasErrors())
        reject(
          error || new Error(stats.toString({ all: false, errors: true })),
        );
      else {
        try {
          verifyDependencies(
            root,
            upstream,
            stats.toJson({
              all: false,
              modules: true,
              nestedModules: true,
              cachedModules: true,
              modulesSpace: Infinity,
              groupModulesByAttributes: false,
              groupModulesByType: false,
              groupModulesByPath: false,
              groupModulesByExtension: false,
              groupModulesByLayer: false,
              groupModulesByCacheStatus: false,
            }).modules,
          );
          console.log(
            stats.toString({ all: false, timings: true, warnings: true }),
          );
          complete();
        } catch (error) {
          reject(error);
        }
      }
    },
  ),
);
for (const path of protectedFiles)
  if (before[path] !== sha256(path))
    throw new Error(`Native source changed: ${path}`);
mkdirSync(resolve(root, "dist"), { recursive: true });
writeFileSync(
  resolve(root, "dist/native-source-integrity.json"),
  JSON.stringify(before, null, 2) + "\n",
);
console.log(
  "Native dashboard bundle built. Steps 1–4 source hashes are unchanged.",
);
