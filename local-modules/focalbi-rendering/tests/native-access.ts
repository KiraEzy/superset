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
import { readFileSync, writeFileSync } from "node:fs";
const fixture = JSON.parse(
  readFileSync(".runtime/resources.json", "utf8").replace(/^\uFEFF/, ""),
).resources.find(
  (resource: { key: string }) => resource.key === "native-demographic-test",
);
assert.ok(fixture, "Provision the unrelated native fixture first");
const deniedDataset = fixture.dataset_id;
const origin = process.env.FOCALBI_TEST_HOST || "http://192.168.10.27:3010";
const provider =
  process.env.FOCALBI_TEST_PROVIDER || "http://192.168.10.27:8088";
const issue = (site = origin, body = "{}") =>
  fetch(origin + "/api/focalbi/guest-token", {
    method: "POST",
    headers: { Origin: site, "Content-Type": "application/json" },
    body,
  });
const config = await (await fetch(origin + "/api/focalbi/config")).json();
const first = await issue();
assert.equal(first.status, 200);
const token = (await first.json()).token;
const claims = JSON.parse(
  Buffer.from(token.split(".")[1], "base64url").toString(),
);
assert.deepEqual(claims.resources, [
  { type: "dashboard", id: config.dashboardUuid },
]);
assert.equal(claims.exp - claims.iat, 300);
assert.equal((await issue("http://untrusted.example")).status, 403);
assert.equal((await issue(origin, '{"dashboardId":17}')).status, 400);
assert.equal(
  (await fetch(origin + "/api/focalbi/config?dashboard=17")).status,
  400,
);
const headers = { "X-GuestToken": token, "Content-Type": "application/json" };
const denied = await fetch(provider + "/api/v1/chart/data", {
  method: "POST",
  headers,
  body: JSON.stringify({
    datasource: { id: deniedDataset, type: "table" },
    force: false,
    result_format: "json",
    result_type: "full",
    queries: [
      {
        columns: ["district"],
        metrics: [
          {
            expressionType: "SIMPLE",
            column: { column_name: "residents" },
            aggregate: "SUM",
            label: "Residents",
          },
        ],
        filters: [],
        extras: {},
        row_limit: 10,
      },
    ],
    form_data: { datasource: `${deniedDataset}__table`, viz_type: "pie" },
  }),
});
assert.equal(
  denied.status,
  403,
  "guest cannot query a different native dataset",
);
const deniedBody = await denied.json();
assert.ok(JSON.stringify(deniedBody).toLowerCase().includes("access"));
const second = (await (await issue()).json()).token;
assert.notEqual(second, token, "renewal gets a distinct token");
const nextClaims = JSON.parse(
  Buffer.from(second.split(".")[1], "base64url").toString(),
);
assert.deepEqual(nextClaims.resources, claims.resources);
writeFileSync(
  "test-results/native-access.json",
  JSON.stringify(
    {
      passed: true,
      incorrectDatasetStatus: denied.status,
      checks: [
        "one approved resource",
        "native dataset access rejection",
        "visitor overrides rejected",
        "untrusted origins rejected",
        "no-store token service",
        "renewal resource unchanged",
      ],
    },
    null,
    2,
  ),
);
console.log("Native guest access checks passed.");
