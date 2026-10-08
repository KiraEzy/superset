/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { createHash } from "node:crypto";

interface Module {
  nameForCondition?: string;
  modules?: Module[];
  children?: Module[];
}
export function verifyDependencies(
  root: string,
  upstream: string,
  modules: Module[],
) {
  const packages: Record<
    string,
    {
      name: string;
      version: string;
      license: string;
      sha256: string;
      files: Record<string, string>;
    }
  > = {};
  const visit = (module: Module) => {
    const resource = module.nameForCondition;
    if (resource?.includes("node_modules")) {
      let directory = dirname(resource);
      while (directory.includes("node_modules")) {
        const path = resolve(directory, "package.json");
        if (existsSync(path)) {
          const buffer = readFileSync(path);
          const metadata = JSON.parse(buffer.toString());
          if (!metadata.name || !metadata.version) {
            directory = dirname(directory);
            continue;
          }
          const base = path.startsWith(resolve(root, "node_modules"))
            ? root
            : upstream;
          const key = `${base === root ? "module" : "upstream"}:${relative(base, directory).replaceAll("\\", "/")}`;
          packages[key] ||= {
            name: metadata.name,
            version: metadata.version,
            license:
              metadata.license ||
              metadata.licenses
                ?.map((item: { type: string }) => item.type)
                .join(" OR "),
            sha256: createHash("sha256").update(buffer).digest("hex"),
            files: {},
          };
          if (!packages[key].license)
            throw new Error(`License metadata missing for ${metadata.name}`);
          packages[key].files[
            relative(directory, resource).replaceAll("\\", "/")
          ] = createHash("sha256").update(readFileSync(resource)).digest("hex");
          break;
        }
        directory = dirname(directory);
      }
    }
    module.modules?.forEach(visit);
    module.children?.forEach(visit);
  };
  modules.forEach(visit);
  const records = Object.fromEntries(
    Object.entries(packages)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([name, record]) => [
        name,
        {
          ...record,
          files: Object.fromEntries(
            Object.entries(record.files).sort(([a], [b]) => a.localeCompare(b)),
          ),
        },
      ]),
  );
  const path = resolve(root, "dependency-provenance.json");
  if (!Object.keys(records).length)
    throw new Error("No bundled dependency records found");
  const serialized = JSON.stringify(records, null, 2) + "\n";
  if (existsSync(path) && readFileSync(path, "utf8") !== serialized)
    throw new Error(
      "Bundled dependency provenance changed. Review and record a compatibility migration.",
    );
  if (!existsSync(path)) writeFileSync(path, serialized);
  console.log(`Verified ${Object.keys(records).length} bundled dependencies`);
}
