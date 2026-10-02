/*
 * Licensed to the Apache Software Foundation (ASF) under one or more
 * contributor license agreements. See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The ASF licenses this file to You under the Apache License, Version 2.0
 * (the "License"); you may not use this file except in compliance with
 * the License. You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import assert from "node:assert/strict";
import test from "node:test";
import jwt from "jsonwebtoken";

const base = "http://localhost:3100";
const superset = "http://localhost:8088";
const dashboardId = Number(process.env.FOCAL_DASHBOARD_ID);
const datasetId = Number(process.env.FOCAL_DATASET_ID);
const uuid = process.env.FOCAL_DASHBOARD_UUID!;
const filterId = process.env.FOCAL_COUNTRY_FILTER_ID!;
async function session(viewer: string): Promise<string> {
  const response = await fetch(base + "/api/demo/session", {
    method: "POST",
    headers: { Origin: base, "Content-Type": "application/json" },
    body: JSON.stringify({ viewer }),
  });
  assert.equal(response.status, 200);
  return response.headers.get("set-cookie")!.split(";")[0];
}
async function token(cookie: string): Promise<string> {
  const response = await fetch(base + "/api/analytics/guest-token", {
    headers: { Cookie: cookie },
  });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  return (await response.json()).token as string;
}
async function countries(guest: string, country?: string): Promise<Response> {
  return fetch(superset + "/api/v1/chart/data", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-GuestToken": guest },
    body: JSON.stringify({
      datasource: { id: datasetId, type: "table" },
      force: true,
      queries: [
        {
          columns: ["country"],
          metrics: [],
          filters: country
            ? [{ col: "country", op: "IN", val: [country] }]
            : [],
          extras: {},
          row_limit: 100,
        },
      ],
      form_data: {
        datasource: `${datasetId}__table`,
        dashboardId,
        type: "NATIVE_FILTER",
        native_filter_id: filterId,
      },
      result_format: "json",
      result_type: "full",
    }),
  });
}
test("anonymous requests cannot obtain dashboard configuration or tokens", async () => {
  for (const route of ["/api/analytics/config", "/api/analytics/guest-token"]) {
    assert.equal((await fetch(base + route)).status, 401);
  }
});
test("cross-origin session creation and unsupported identities are rejected", async () => {
  const evil = await fetch(base + "/api/demo/session", {
    method: "POST",
    headers: {
      Origin: "https://untrusted.example",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ viewer: "usa" }),
  });
  assert.equal(evil.status, 403);
  const invalid = await fetch(base + "/api/demo/session", {
    method: "POST",
    headers: { Origin: base, "Content-Type": "application/json" },
    body: JSON.stringify({ viewer: "admin" }),
  });
  assert.equal(invalid.status, 400);
});
test("signed guest token is limited to one dashboard and five minutes", async () => {
  const cookie = await session("usa");
  const guest = await token(cookie);
  const claims = jwt.verify(guest, process.env.FOCAL_EMBED_SECRET!, {
    algorithms: ["HS256"],
    audience: "focalbi-embedded",
  }) as jwt.JwtPayload;
  assert.deepEqual(claims.resources, [{ type: "dashboard", id: uuid }]);
  assert.deepEqual(claims.rls_rules, [
    { dataset: datasetId, clause: "country = 'USA'" },
  ]);
  assert.equal(claims.exp! - claims.iat!, 300);
  assert.equal(
    (
      await fetch(base + "/api/analytics/guest-token?country=France", {
        headers: { Cookie: cookie },
      })
    ).status,
    400,
  );
});
test("dashboard frame allows the demo origin and rejects another origin", async () => {
  const good = await fetch(superset + "/embedded/" + uuid, {
    headers: { Referer: base + "/" },
  });
  assert.equal(good.status, 200);
  assert.match(
    good.headers.get("content-security-policy")!,
    /frame-ancestors[^;]*http:\/\/localhost:3100/,
  );
  assert.equal(good.headers.get("x-frame-options"), null);
  const bad = await fetch(superset + "/embedded/" + uuid, {
    headers: { Referer: "https://untrusted.example/" },
  });
  assert.equal(bad.status, 403);
});
test("guest can read its dashboard but cannot read another dashboard or edit", async () => {
  const guest = await token(await session("usa"));
  const headers = { "X-GuestToken": guest };
  assert.equal(
    (await fetch(`${superset}/api/v1/dashboard/${dashboardId}`, { headers }))
      .status,
    200,
  );
  assert.ok(
    [403, 404].includes(
      (await fetch(superset + "/api/v1/dashboard/1", { headers })).status,
    ),
  );
  const write = await fetch(`${superset}/api/v1/dashboard/${dashboardId}`, {
    method: "PUT",
    headers: { ...headers, "Content-Type": "application/json" },
    body: "{}",
  });
  assert.ok([400, 401, 403].includes(write.status));
});
for (const [viewer, expected] of [
  ["usa", "USA"],
  ["france", "France"],
]) {
  test(`live queries enforce ${expected} row-level security`, async () => {
    const guest = await token(await session(viewer));
    const response = await countries(guest);
    const result = await response.json();
    assert.equal(response.status, 200, JSON.stringify(result));
    assert.deepEqual(result.result[0].data, [{ country: expected }]);
    const opposite = await countries(
      guest,
      expected === "USA" ? "France" : "USA",
    );
    const oppositeData = await opposite.json();
    assert.equal(opposite.status, 200, JSON.stringify(oppositeData));
    assert.deepEqual(oppositeData.result[0].data, []);
  });
}
test("expired and tampered guest tokens cannot query Superset", async () => {
  const guest = await token(await session("usa"));
  const claims = jwt.decode(guest) as jwt.JwtPayload;
  const expired = jwt.sign(
    { ...claims, exp: Math.floor(Date.now() / 1000) - 60 },
    process.env.FOCAL_EMBED_SECRET!,
    { algorithm: "HS256" },
  );
  for (const invalid of [expired, guest.slice(0, -8) + "AAAAAAAA"]) {
    // Superset masks inaccessible dashboards as 404 for anonymous requests.
    assert.ok(
      [401, 403, 404].includes(
        (
          await fetch(`${superset}/api/v1/dashboard/${dashboardId}`, {
            headers: { "X-GuestToken": invalid },
          })
        ).status,
      ),
    );
  }
});
test("switching viewers rotates the session; logout stops token issuance", async () => {
  const old = await session("usa");
  const switched = await fetch(base + "/api/demo/session", {
    method: "POST",
    headers: { Cookie: old, Origin: base, "Content-Type": "application/json" },
    body: JSON.stringify({ viewer: "france" }),
  });
  const current = switched.headers.get("set-cookie")!.split(";")[0];
  assert.notEqual(old, current);
  assert.equal(
    (
      await fetch(base + "/api/analytics/guest-token", {
        headers: { Cookie: old },
      })
    ).status,
    401,
  );
  const out = await fetch(base + "/api/logout", {
    method: "POST",
    headers: {
      Cookie: current,
      Origin: base,
      "Content-Type": "application/json",
    },
    body: "{}",
  });
  assert.equal(out.status, 204);
  assert.equal(
    (
      await fetch(base + "/api/analytics/guest-token", {
        headers: { Cookie: current },
      })
    ).status,
    401,
  );
});
