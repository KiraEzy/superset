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
type Point =
  | number
  | null
  | undefined
  | unknown[]
  | { value?: number | null | unknown[] };
interface Axis {
  type?: string;
  data?: unknown[];
}
interface Options {
  series?: { type?: string; data?: Point[] }[];
  xAxis?: Axis | Axis[];
  yAxis?: Axis | Axis[];
}

/** Honor native sum sorting for one categorical bar series. Query/rank membership
 * is unchanged; the native transform already handles multi-series sorting. */
export function sortCategoryBars<T extends { echartOptions?: unknown }>(
  props: T,
  controls: {
    xAxisSort?: unknown;
    xAxisSortAsc?: unknown;
    orientation?: unknown;
  },
): T {
  if (
    controls.xAxisSort !== "sum" ||
    typeof controls.xAxisSortAsc !== "boolean"
  )
    return props;
  const options = props.echartOptions as Options | undefined;
  if (
    !options ||
    options.series?.length !== 1 ||
    options.series[0].type !== "bar"
  )
    return props;
  const horizontal = controls.orientation === "horizontal";
  const axisKey = horizontal ? "yAxis" : "xAxis";
  const axis = options[axisKey];
  const category = Array.isArray(axis) ? axis[0] : axis;
  const data = options.series[0].data;
  if (category?.type !== "category" || !data) return props;
  const values = data.map((point) => {
    const value =
      point !== null && typeof point === "object" && !Array.isArray(point)
        ? point.value
        : point;
    return Array.isArray(value) ? value[horizontal ? 0 : 1] : value;
  });
  // Preserve native null/undefined handling instead of inventing numeric values.
  if (
    !values.every(
      (value) => typeof value === "number" && Number.isFinite(value),
    )
  )
    return props;
  const order = values
    .map((value, index) => ({ value: value as number, index }))
    .sort(
      (left, right) =>
        (left.value - right.value) * (controls.xAxisSortAsc ? 1 : -1),
    );
  const sortedAxis = {
    ...category,
    ...(category.data?.length === data.length
      ? { data: order.map(({ index }) => category.data![index]) }
      : {}),
  };
  return {
    ...props,
    echartOptions: {
      ...options,
      [axisKey]: Array.isArray(axis)
        ? [sortedAxis, ...axis.slice(1)]
        : sortedAxis,
      series: [
        { ...options.series[0], data: order.map(({ index }) => data[index]) },
      ],
    },
  };
}
