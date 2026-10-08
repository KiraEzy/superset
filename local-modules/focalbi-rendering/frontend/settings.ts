/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership. The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License. You may obtain a copy of the License at
 * http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
export type Engine = "baseline" | "fork";

export const capabilities: Record<
  string,
  { highlight: boolean; layering: boolean }
> = {
  big_number_total: { highlight: false, layering: false },
  pie: { highlight: true, layering: false },
  echarts_timeseries_bar: { highlight: true, layering: false },
  mixed_timeseries: { highlight: false, layering: true },
  table: { highlight: false, layering: false },
};

export interface PresentationSettings {
  version: 1;
  title?: { filterId: string; single: string; multiple: string };
  highlight?: {
    filterId: string;
    dimension: string;
    selectedColors: string[];
    otherColor: string;
    labelColors?: Record<string, string>;
  };
  secondaryBehindPrimary?: boolean;
}

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const color = (value: unknown): value is string =>
  typeof value === "string" && /^#[\da-f]{6}$/i.test(value);

/** Validate optional layout metadata without accepting query or data settings. */
export function readSettings(value: unknown): PresentationSettings | undefined {
  if (!record(value) || value.version !== 1) return undefined;
  const allowed = ["version", "title", "highlight", "secondaryBehindPrimary"];
  if (Object.keys(value).some((key) => !allowed.includes(key)))
    return undefined;
  if (value.title !== undefined) {
    const title = value.title;
    if (
      !record(title) ||
      typeof title.filterId !== "string" ||
      !title.filterId ||
      typeof title.single !== "string" ||
      typeof title.multiple !== "string" ||
      Object.keys(title).some(
        (key) => !["filterId", "single", "multiple"].includes(key),
      )
    )
      return undefined;
  }
  if (value.highlight !== undefined) {
    const highlight = value.highlight;
    if (
      !record(highlight) ||
      typeof highlight.filterId !== "string" ||
      !highlight.filterId ||
      typeof highlight.dimension !== "string" ||
      !highlight.dimension ||
      !color(highlight.otherColor) ||
      !Array.isArray(highlight.selectedColors) ||
      !highlight.selectedColors.length ||
      !highlight.selectedColors.every(color) ||
      Object.keys(highlight).some(
        (key) =>
          ![
            "filterId",
            "dimension",
            "selectedColors",
            "otherColor",
            "labelColors",
          ].includes(key),
      )
    )
      return undefined;
    if (
      highlight.labelColors !== undefined &&
      (!record(highlight.labelColors) ||
        !Object.values(highlight.labelColors).every(color))
    )
      return undefined;
  }
  if (
    value.secondaryBehindPrimary !== undefined &&
    typeof value.secondaryBehindPrimary !== "boolean"
  )
    return undefined;
  return value as unknown as PresentationSettings;
}

/** Titles describe applied selections; saved native chart names remain intact. */
export function selectionTitle(
  settings: PresentationSettings["title"],
  values: unknown[],
  fallback: string,
): string {
  if (!settings || !values.length) return fallback;
  return values.length === 1
    ? settings.single.replaceAll("{selection}", String(values[0]))
    : settings.multiple;
}

/** Stable entity colors do not depend on ranking or selection order. */
export function entityColor(
  entity: string,
  palette: string[],
  overrides: Record<string, string> = {},
): string {
  if (overrides[entity]) return overrides[entity];
  let hash = 2166136261;
  for (const character of entity)
    hash = Math.imul(hash ^ character.charCodeAt(0), 16777619);
  return palette[(hash >>> 0) % palette.length];
}

/** Resolve collisions deterministically within a selected set. */
export function selectionColors(
  values: unknown[],
  highlight: NonNullable<PresentationSettings["highlight"]>,
): Map<string, string> {
  const result = new Map<string, string>();
  const used = new Set<string>();
  [...new Set(values.map(String))].sort().forEach((entity) => {
    let selected = entityColor(
      entity,
      highlight.selectedColors,
      highlight.labelColors,
    );
    if (!highlight.labelColors?.[entity] && used.has(selected)) {
      const unused = highlight.selectedColors.find(
        (candidate) => !used.has(candidate),
      );
      if (unused) selected = unused;
      else {
        let hash = 2166136261;
        for (const character of entity)
          hash = Math.imul(hash ^ character.charCodeAt(0), 16777619);
        do {
          selected =
            "#" +
            (((hash >>> 0) & 0x9f9f9f) | 0x404040)
              .toString(16)
              .padStart(6, "0");
          hash = Math.imul(hash + 1, 16777619);
        } while (used.has(selected));
      }
    }
    result.set(entity, selected);
    used.add(selected);
  });
  return result;
}
