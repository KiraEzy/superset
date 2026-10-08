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
import { sortCategoryBars } from "../frontend/category-sort.ts";

test("horizontal and vertical value sorting preserve category/value pairs and source inputs", () => {
  for (const horizontal of [true, false]) {
    const axis = horizontal ? "yAxis" : "xAxis";
    const points = [
      ["North", 12],
      ["Central", -2],
      ["West", 6],
    ];
    const input = {
      echartOptions: {
        [axis]: { type: "category", data: points.map((point) => point[0]) },
        series: [
          {
            type: "bar",
            data: points.map((point) => ({
              value: horizontal ? [...point].reverse() : [...point],
            })),
          },
        ],
      },
    };
    const original = JSON.stringify(input);
    const sorted = sortCategoryBars(input, {
      xAxisSort: "sum",
      xAxisSortAsc: true,
      orientation: horizontal ? "horizontal" : "vertical",
    });
    const options = sorted.echartOptions as typeof input.echartOptions;
    assert.deepEqual(options[axis].data, ["Central", "West", "North"]);
    assert.deepEqual(
      options.series[0].data.map((point) => point.value[horizontal ? 0 : 1]),
      [-2, 6, 12],
    );
    assert.equal(JSON.stringify(input), original);
    const descending = sortCategoryBars(sorted, {
      xAxisSort: "sum",
      xAxisSortAsc: false,
      orientation: horizontal ? "horizontal" : "vertical",
    });
    assert.deepEqual(
      (descending.echartOptions as typeof input.echartOptions)[axis].data,
      ["North", "West", "Central"],
    );
  }
});

test("multi-series, unknown sort settings and undefined values retain native behavior", () => {
  const nullPoints = {
    echartOptions: {
      yAxis: { type: "category" },
      series: [{ type: "bar", data: [null, undefined] }],
    },
  };
  assert.equal(
    sortCategoryBars(nullPoints, {
      xAxisSort: "sum",
      xAxisSortAsc: true,
      orientation: "horizontal",
    }),
    nullPoints,
  );
  const input = {
    echartOptions: {
      yAxis: { type: "category", data: ["North"] },
      series: [{ type: "bar", data: [{ value: [null, "North"] }] }],
    },
  };
  assert.equal(
    sortCategoryBars(input, {
      xAxisSort: "sum",
      xAxisSortAsc: true,
      orientation: "horizontal",
    }),
    input,
  );
  assert.equal(
    sortCategoryBars(input, { xAxisSort: "name", xAxisSortAsc: true }),
    input,
  );
  const multi = {
    echartOptions: {
      ...input.echartOptions,
      series: [...input.echartOptions.series, ...input.echartOptions.series],
    },
  };
  assert.equal(
    sortCategoryBars(multi, {
      xAxisSort: "sum",
      xAxisSortAsc: true,
      orientation: "horizontal",
    }),
    multi,
  );
});
