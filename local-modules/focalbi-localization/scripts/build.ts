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
import { fileURLToPath } from "node:url";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const upstream = resolve(root, "../../superset-frontend");
const rendering = resolve(root, "../focalbi-rendering");
const combined = process.argv.includes("--with-rendering");
const editorOnly = process.argv.includes("--editor-only");
const mode = combined ? "combined" : "native";
const require = createRequire(resolve(upstream, "package.json"));
process.chdir(upstream);
process.env.NODE_ENV = "production";
process.env.CI = "true";
process.env.BROWSERSLIST_IGNORE_OLD_DATA = "true";
process.argv.push("--mode=production");
const webpack = require("webpack");
const config = require(resolve(upstream, "webpack.config.js"));
const nativePaths: Record<string, string> = {
  DashboardBuilder:
    "src/dashboard/components/DashboardBuilder/DashboardBuilder.tsx",
  SliceHeader: "src/dashboard/components/SliceHeader/index.tsx",
  SuperChartCore:
    "packages/superset-ui-core/src/chart/components/SuperChartCore.tsx",
  DataTable: "plugins/plugin-chart-table/src/DataTable/index.tsx",
  DashboardHeader: "src/dashboard/components/Header/index.tsx",
  Explore: "src/explore/components/ExploreViewContainer/index.tsx",
  ExploreHeader: "src/explore/components/ExploreChartHeader/index.tsx",
  Dataset:
    "src/components/Datasource/components/DatasourceEditor/DatasourceEditor.tsx",
  Chart: "src/dashboard/components/gridComponents/Chart/Chart.tsx",
  Tab: "src/dashboard/components/gridComponents/Tab/Tab.tsx",
  Markdown: "src/dashboard/components/gridComponents/Markdown/Markdown.tsx",
  GridHeader: "src/dashboard/components/gridComponents/Header/Header.tsx",
  FilterControl:
    "src/dashboard/components/nativeFilters/FilterBar/FilterControls/FilterControl.tsx",
};
for (const [name, path] of Object.entries(nativePaths)) {
  config.resolve.alias[`focalbi-native/${name}$`] = resolve(upstream, path);
  config.resolve.alias[`focalbi-host/${name}$`] =
    combined &&
    ["DashboardBuilder", "SliceHeader", "SuperChartCore", "DataTable"].includes(
      name,
    )
      ? resolve(rendering, `frontend/${name}.tsx`)
      : resolve(upstream, path);
}
config.resolve.modules.push(
  resolve(rendering, "node_modules"),
  resolve(upstream, "node_modules"),
);
config.resolveLoader = { modules: [resolve(upstream, "node_modules")] };
config.output.path = resolve(root, `dist/${mode}/assets`);
config.output.clean = false;
config.cache = {
  type: "filesystem",
  cacheDirectory: resolve(root, `.build/${mode}`),
  buildDependencies: { config: [fileURLToPath(import.meta.url)] },
};
config.optimization.minimize = false;
config.devtool = false;
config.plugins = config.plugins.filter(
  (plugin: { constructor: { name: string } }) =>
    !["BundleAnalyzerPlugin", "VisualizerPlugin", "ProgressPlugin"].includes(
      plugin.constructor.name,
    ),
);
const sharedModules = {
  "@superset-ui/core": { singleton: true, eager: true },
  "@superset-ui/core/components": { singleton: true, eager: true },
  "@emotion/react": { singleton: true, eager: true },
  "@emotion/styled": { singleton: true, eager: true },
};
for (const plugin of config.plugins)
  if (plugin.constructor.name === "ModuleFederationPlugin")
    Object.assign(plugin._options.shared, sharedModules);
for (const rule of config.module.rules)
  if (rule.test?.test("module.css"))
    rule.include = [...rule.include, root, rendering];
const displaySources = [
  "packages/superset-ui-core/src/components/EditableTitle/index.tsx",
  "packages/superset-ui-core/src/components/DynamicEditableTitle/index.tsx",
  nativePaths.FilterControl,
  nativePaths.Chart,
  "src/explore/components/ExploreChartHeader/useExploreMetadataBar.tsx",
  "src/filters/components/Select/SelectFilterPlugin.tsx",
  "src/dashboard/components/nativeFilters/FilterBar/Header/index.tsx",
  "src/dashboard/components/nativeFilters/FilterBar/ActionButtons/index.tsx",
  "plugins/plugin-chart-echarts/src/Timeseries/EchartsTimeseries.tsx",
  "plugins/plugin-chart-table/src/DataTable/DataTable.tsx",
  "plugins/plugin-chart-table/src/TableChart.tsx",
];
const moduleDisplaySources = combined
  ? [
      "frontend/DashboardBuilder.tsx",
      "vendor/baseline/echarts/Timeseries/EchartsTimeseries.tsx",
      "vendor/fork/echarts/Timeseries/EchartsTimeseries.tsx",
      "vendor/baseline/table/DataTable/DataTable.tsx",
      "vendor/fork/table/DataTable/DataTable.tsx",
      "vendor/baseline/table/TableChart.tsx",
      "vendor/fork/table/TableChart.tsx",
    ].map((path) => resolve(rendering, path))
  : [];
config.module.rules.push({
  enforce: "pre",
  include: [
    ...displaySources.map((path) => resolve(upstream, path)),
    ...moduleDisplaySources,
  ],
  use: [
    {
      loader: resolve(root, "scripts/source-loader.cts"),
      options: {
        hooks: resolve(root, "frontend/hooks.ts").replaceAll("\\", "/"),
      },
    },
  ],
});
const thinWrappers = [
  "DashboardHeader",
  "Explore",
  "ExploreHeader",
  "Dataset",
  "Chart",
  "Tab",
  "Markdown",
  "GridHeader",
  "FilterControl",
];
mkdirSync(resolve(root, ".build/wrappers"), { recursive: true });
for (const name of thinWrappers)
  writeFileSync(
    resolve(root, `.build/wrappers/${name}.tsx`),
    `export { ${name} as default${name === "Tab" ? ", RENDER_TAB, RENDER_TAB_CONTENT" : ""} } from ${JSON.stringify(resolve(root, "frontend/HostSurfaces.tsx").replaceAll("\\", "/"))};`,
  );
config.plugins.push(
  new webpack.NormalModuleReplacementPlugin(
    /DashboardBuilder|SliceHeader|SuperChartCore|ExploreViewContainer|ExploreChartHeader|DatasourceEditor|Chart|Tab|Markdown|Header|FilterControl|setupPluginsExtra|DataTable/,
    (resource: { request: string; context: string }) => {
      if (
        resource.request.startsWith("focalbi-native/") ||
        resource.request.startsWith("focalbi-host/")
      )
        return;
      if (
        combined &&
        resource.request === "./DataTable" &&
        /\/vendor\/(baseline|fork)\/table$/.test(
          resource.context.replaceAll("\\", "/"),
        )
      ) {
        resource.request = resolve(root, "frontend/DataTable.tsx");
        return;
      }
      const aliased = /^(src|plugins|packages)\//.test(resource.request);
      const candidate = resolve(
        aliased ? upstream : resource.context,
        resource.request,
      ).replaceAll("\\", "/");
      for (const [name, path] of Object.entries(nativePaths)) {
        const absolute = resolve(upstream, path).replaceAll("\\", "/");
        const stem = absolute.replace(/\.tsx$/, "");
        const matches =
          candidate === absolute ||
          candidate === stem ||
          (stem.endsWith("/index") && candidate === stem.slice(0, -6)) ||
          resource.request === path.replace(/\.tsx$/, "");
        if (!matches) continue;
        if (name === "DataTable") {
          resource.request = resolve(root, "frontend/DataTable.tsx");
          return;
        }
        resource.request = thinWrappers.includes(name)
          ? resolve(root, `.build/wrappers/${name}.tsx`)
          : resolve(root, `frontend/${name}.tsx`);
        return;
      }
      if (
        combined &&
        (resource.request.endsWith("/setupPluginsExtra") ||
          resource.request === "./setupPluginsExtra")
      )
        resource.request = resolve(rendering, "frontend/setupPluginsExtra.ts");
    },
  ),
);
const protectedPaths = [
  ...Object.values(nativePaths),
  ...displaySources,
  "src/dashboard/containers/DashboardPage.tsx",
  "src/dashboard/util/charts/getFormDataWithExtraFilters.ts",
  "src/components/Chart/chartAction.ts",
  "src/explore/exploreUtils/index.ts",
  "plugins/plugin-chart-echarts/src/Pie/buildQuery.ts",
  "plugins/plugin-chart-echarts/src/Timeseries/buildQuery.ts",
  "plugins/plugin-chart-echarts/src/MixedTimeseries/buildQuery.ts",
  "plugins/plugin-chart-table/src/buildQuery.ts",
];
const hash = (path: string) =>
  createHash("sha256")
    .update(readFileSync(resolve(upstream, path)))
    .digest("hex");
const hashes = Object.fromEntries(
  protectedPaths.map((path) => [path, hash(path)]),
);
const compatibilityFile = resolve(root, "compatibility.json");
if (process.argv.includes("--record-compatibility"))
  writeFileSync(
    compatibilityFile,
    JSON.stringify(
      {
        superset: "6.1.0",
        revision: execFileSync("git", ["rev-parse", "HEAD"], {
          cwd: resolve(root, "../.."),
          encoding: "utf8",
        }).trim(),
        files: hashes,
      },
      null,
      2,
    ),
  );
const compatibility = JSON.parse(readFileSync(compatibilityFile, "utf8"));
for (const [path, expected] of Object.entries(compatibility.files))
  if (hash(path) !== expected)
    throw new Error(`Compatibility review required: ${path}`);
if (combined)
  execFileSync(
    "python",
    [resolve(rendering, "scripts/snapshot.py"), "--verify"],
    { stdio: "inherit" },
  );
async function compile(configuration: unknown) {
  await new Promise<void>((complete, reject) =>
    webpack(
      configuration,
      (
        error: Error | null,
        stats: {
          hasErrors: () => boolean;
          toString: (options: object) => string;
        },
      ) => {
        if (error || stats.hasErrors())
          reject(
            error || new Error(stats.toString({ all: false, errors: true })),
          );
        else {
          console.log(
            stats.toString({ all: false, timings: true, warnings: true }),
          );
          complete();
        }
      },
    ),
  );
}
if (!editorOnly) await compile(config);
// Federation shares the same React/Ant Design versions as the native host.
const editor = {
  ...config,
  name: "localization-editor",
  entry: {},
  output: {
    ...config.output,
    path: resolve(root, "dist/extension/frontend/dist"),
    filename: "[name].js",
    chunkFilename: "[id].js",
    publicPath: "auto",
    uniqueName: "focalbi_contentLocalization",
  },
  plugins: [
    new (require("mini-css-extract-plugin"))({ filename: "[name].css" }),
    new webpack.container.ModuleFederationPlugin({
      name: "focalbi_contentLocalization",
      filename: "remoteEntry.js",
      exposes: {
        "./index": resolve(root, "frontend/index.tsx"),
        "./Dialog": resolve(root, "frontend/TranslationsDialog.tsx"),
      },
      shared: {
        react: { singleton: true, requiredVersion: "16.14.0" },
        "react-dom": { singleton: true, requiredVersion: "16.14.0" },
        antd: { singleton: true },
        ...Object.fromEntries(
          Object.keys(sharedModules).map((name) => [
            name,
            { singleton: true, import: false },
          ]),
        ),
      },
    }),
  ],
  optimization: {
    ...config.optimization,
    runtimeChunk: false,
    splitChunks: false,
  },
  cache: false,
};
await compile(editor);
for (const [path, before] of Object.entries(hashes))
  if (hash(path) !== before)
    throw new Error(`Protected native source changed: ${path}`);
execFileSync("python", [resolve(root, "scripts/package.py")], {
  stdio: "inherit",
});
console.log(
  `Localization ${mode} build completed; protected native files unchanged.`,
);
