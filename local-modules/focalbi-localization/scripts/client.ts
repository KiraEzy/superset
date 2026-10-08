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
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(
  resolve(root, "../../superset-frontend/package.json"),
);
const ts = require("typescript");
const output = resolve(root, "dist/client");
mkdirSync(output, { recursive: true });
for (const file of ["LICENSE.txt", "NOTICE"]) copyFileSync(resolve(root, file), resolve(output, file));
const files = ["contracts", "embedding"].map((name) =>
  resolve(root, `frontend/${name}.ts`),
);
for (const name of ["contracts", "embedding"]) {
  const source = readFileSync(resolve(root, `frontend/${name}.ts`), "utf8");
  const result = ts
    .transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2020,
      },
    })
    .outputText.replaceAll('"./contracts"', '"./contracts.js"');
  writeFileSync(resolve(output, `${name}.js`), result);
}
ts.createProgram(files, {
  declaration: true,
  emitDeclarationOnly: true,
  outDir: output,
  target: ts.ScriptTarget.ES2020,
  module: ts.ModuleKind.ESNext,
  skipLibCheck: true,
}).emit();
writeFileSync(
  resolve(output, "package.json"),
  JSON.stringify(
    {
      name: "@focalbi/content-localization-client",
      version: "1.0.0",
      type: "module",
      main: "embedding.js",
      types: "embedding.d.ts",
      exports: {
        ".": { types: "./embedding.d.ts", default: "./embedding.js" },
        "./contracts": { types: "./contracts.d.ts", default: "./contracts.js" },
      },
      files: ["*.js", "*.d.ts", "LICENSE.txt", "NOTICE"],
      license: "Apache-2.0",
    },
    null,
    2,
  ),
);
execFileSync(
  process.platform === "win32" ? "npm.cmd" : "npm",
  ["pack", "--ignore-scripts"],
  { cwd: output, stdio: "inherit", shell: process.platform === "win32" },
);
