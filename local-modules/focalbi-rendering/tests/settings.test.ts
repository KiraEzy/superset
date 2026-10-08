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
import { test } from "node:test";
import {
  readSettings,
  selectionTitle,
  selectionColors,
} from "../frontend/settings.ts";
test("presentation rejects query/aggregation settings and malformed nested controls", () => {
  assert.deepEqual(readSettings({ version: 1 }), { version: 1 });
  for (const key of [
    "sql",
    "datasetId",
    "dashboardId",
    "filters",
    "metric",
    "denominator",
    "row_limit",
  ]) {
    assert.equal(readSettings({ version: 1, [key]: "arbitrary" }), undefined);
  }
  assert.equal(
    readSettings({
      version: 1,
      title: { filterId: "", single: "x", multiple: "y" },
    }),
    undefined,
  );
  assert.equal(
    readSettings({
      version: 1,
      title: {
        filterId: "selection",
        single: "x",
        multiple: "y",
        sql: "SELECT 1",
      },
    }),
    undefined,
  );
  assert.equal(
    readSettings({ version: 1, secondaryBehindPrimary: "yes" }),
    undefined,
  );
  assert.equal(
    readSettings({
      version: 1,
      highlight: {
        filterId: "selection",
        dimension: "",
        otherColor: "#112233",
        selectedColors: ["#445566"],
      },
    }),
    undefined,
  );
});
test("titles work for unrelated entities, multiple selections, empty values and literal HTML", () => {
  const settings = {
    filterId: "district-selector",
    single: "{selection} residents",
    multiple: "Residents",
  };
  assert.equal(
    selectionTitle(settings, ["North"], "Native heading"),
    "North residents",
  );
  assert.equal(
    selectionTitle(settings, ["North", "West"], "Native heading"),
    "Residents",
  );
  assert.equal(
    selectionTitle(settings, [], "Native heading"),
    "Native heading",
  );
  assert.equal(
    selectionTitle(settings, ["<b>North</b>"], "Native heading"),
    "<b>North</b> residents",
  );
});
test("entity colors match across ranking/order changes and selections beyond the palette", () => {
  const settings = {
    filterId: "district-selector",
    dimension: "district",
    selectedColors: ["#66B3E1", "#318AC2"],
    otherColor: "#142D59",
    labelColors: { North: "#79C7B0" },
  };
  const entities = Array.from(
    { length: 64 },
    (_, index) => `District ${index}`,
  ).concat("North");
  const first = selectionColors(entities, settings),
    second = selectionColors([...entities].reverse(), settings);
  assert.deepEqual(first, second);
  assert.equal(new Set(first.values()).size, entities.length);
  assert.equal(first.get("North"), "#79C7B0");
});
