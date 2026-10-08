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
export interface DisplayState {
  legends?: { selected?: Record<string, boolean>; scrollDataIndex?: number }[];
  zoom?: { start?: number; end?: number }[];
}
export interface DisplayOptions {
  series?: unknown;
  legend?: DisplayState["legends"];
  dataZoom?: DisplayState["zoom"];
}
/** Native JSON results may be repackaged without a data change. */
export function sameResultData(
  previous: readonly unknown[],
  next: readonly unknown[],
): boolean {
  if (previous.length !== next.length) return false;
  return previous.every((value, index) => {
    if (value === next[index]) return true;
    try {
      return JSON.stringify(value) === JSON.stringify(next[index]);
    } catch {
      return false;
    }
  });
}
/** Feed remembered raw display keys to both engines before a native redraw. */
export function retainDisplayProps(
  raw: Record<string, unknown>,
  saved: DisplayState,
): Record<string, unknown> {
  if (!saved.legends?.length && !saved.zoom?.length) return raw;
  const source = raw.echartOptions;
  if (!source || typeof source !== "object" || Array.isArray(source))
    return raw;
  const options = source as Record<string, unknown>;
  const merge = (value: unknown, state: readonly object[] | undefined) => {
    if (!state?.length || !value || typeof value !== "object") return value;
    const values = Array.isArray(value) ? value : [value];
    const next = values.map((item, index) => ({ ...item, ...state[index] }));
    return Array.isArray(value) ? next : next[0];
  };
  return {
    ...raw,
    echartOptions: {
      ...options,
      legend: merge(options.legend, saved.legends),
      dataZoom: merge(options.dataZoom, saved.zoom),
    },
  };
}
export function needsDisplayRestore(
  options: DisplayOptions,
  saved: DisplayState,
): boolean {
  return (
    !!saved.zoom?.some(
      (value, index) =>
        (value.start !== undefined &&
          value.start !== options.dataZoom?.[index]?.start) ||
        (value.end !== undefined &&
          value.end !== options.dataZoom?.[index]?.end),
    ) ||
    !!saved.legends?.some(
      (value, index) =>
        (value.scrollDataIndex !== undefined &&
          value.scrollDataIndex !== options.legend?.[index]?.scrollDataIndex) ||
        Object.entries(value.selected || {}).some(
          ([key, selected]) =>
            selected !== options.legend?.[index]?.selected?.[key],
        ),
    )
  );
}
