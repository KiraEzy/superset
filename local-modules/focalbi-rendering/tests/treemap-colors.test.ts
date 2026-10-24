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
import test from "node:test";
import { colorTreemapGroups } from "../frontend/treemap-colors.ts";

const fixture = () => ({
  echartOptions: {
    series: [
      {
        type: "treemap",
        data: [
          {
            name: "Revenue",
            value: 60,
            children: [
              {
                name: "Hardware",
                value: 40,
                children: [
                  {
                    name: "North",
                    value: 30,
                    itemStyle: { color: "#ff0000", colorAlpha: 0.3 },
                  },
                  { name: "South", value: 10 },
                ],
              },
              {
                name: "Services",
                value: 20,
                children: [{ name: "North", value: 20 }],
              },
              { name: "Unconfigured", value: 0, children: [] },
            ],
          },
        ],
      },
    ],
  },
});
const colors = { Hardware: "#1677a8", Services: "#218c6f" };
const groups = (value: Record<string, unknown>) =>
  (value.echartOptions as ReturnType<typeof fixture>["echartOptions"]).series[0]
    .data[0].children;

test("parent colours decorate unrelated hierarchies without changing source values or interaction styles", () => {
  const input = fixture();
  const before = structuredClone(input);
  const output = colorTreemapGroups(input, colors);
  assert.deepEqual(input, before);
  assert.deepEqual(
    groups(output).map((g) => [
      g.name,
      g.value,
      g.children.map((c) => [c.name, c.value]),
    ]),
    groups(input).map((g) => [
      g.name,
      g.value,
      g.children.map((c) => [c.name, c.value]),
    ]),
  );
  const branches = groups(output);
  assert.equal(branches[0].children[0].itemStyle?.colorAlpha, 0.3);
  assert.notEqual(
    branches[0].children[0].itemStyle?.color,
    branches[1].children[0].itemStyle?.color,
  );
  assert.equal(branches[2], groups(input)[2]);
});

test("shades remain stable when siblings disappear, sort changes, and metric values change", () => {
  const before = groups(colorTreemapGroups(fixture(), colors))[0].children[0]
    .itemStyle?.color;
  const filtered = fixture();
  filtered.echartOptions.series[0].data[0].children[0].children.pop();
  filtered.echartOptions.series[0].data[0].children[0].children[0].value = 999;
  filtered.echartOptions.series[0].data[0].children.reverse();
  const after = groups(colorTreemapGroups(filtered, colors)).find(
    (g) => g.name === "Hardware",
  )?.children[0].itemStyle?.color;
  assert.equal(after, before);
});

test("absent and malformed settings preserve native rendering", () => {
  const input = fixture();
  for (const invalid of [
    undefined,
    null,
    {},
    [],
    { Hardware: "red" },
    { Hardware: 42 },
  ]) {
    assert.equal(colorTreemapGroups(input, invalid), input);
  }
  const bar = { echartOptions: { series: [{ type: "bar", data: [1, 2] }] } };
  assert.equal(
    (colorTreemapGroups(bar, colors).echartOptions as typeof bar.echartOptions)
      .series[0],
    bar.echartOptions.series[0],
  );
});
