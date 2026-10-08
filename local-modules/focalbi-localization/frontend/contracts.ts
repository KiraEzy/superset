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
export const locales = ["en", "zh-Hant", "zh-Hans"] as const;
export type Locale = (typeof locales)[number];
export type ResourceType = "dashboard" | "chart" | "dataset";
export type Scalar = string | number | boolean | null;
export interface Field {
  key: string;
  label: string;
  source: string;
  sourceHash: string;
  kind: "text" | "markdown" | "template" | "category";
  target?: string;
}
export interface Entry {
  sourceHash: string;
  values: Partial<Record<Locale, string>>;
  dictionary: { value: Scalar; values: Partial<Record<Locale, string>> }[];
}
export interface Catalog {
  version: 1;
  type: ResourceType;
  uuid: string;
  revision: number;
  fields: Field[];
  entries: Record<string, Entry>;
  supportedVizTypes: string[];
  unsupportedVisualizations?: { title: string; type: string }[];
}
export interface Resource {
  uuid: string;
  fields: Field[];
  revision: number;
  translations: Record<
    string,
    { text?: string; dictionary: { value: Scalar; label: string }[] }
  >;
}
export interface Bundle {
  version: 1;
  locale: Locale;
  kind: ResourceType;
  uuid: string;
  resources: Record<string, Resource>;
  charts: Record<string, { uuid: string; datasetUuid: string | null }>;
  datasets: Record<string, string>;
  allowedOrigins: string[];
}
export const apiRoot = "/extensions/focalbi/content-localization/catalog";
export const bridgeType = "focalbi-content-locale";
export const bridgeVersion = 1;
export const localeParam = "content_locale";
export function normalizeLocale(
  value: string | null | undefined,
): Locale | undefined {
  const language = (value || "").toLowerCase().replace(/_/g, "-");
  if (language === "en" || language.startsWith("en-")) return "en";
  if (
    ["hant", "zh-tw", "zh-hk", "zh-mo"].includes(language) ||
    language.startsWith("zh-hant")
  )
    return "zh-Hant";
  if (
    ["hans", "zh", "zh-cn", "zh-sg"].includes(language) ||
    language.startsWith("zh-hans")
  )
    return "zh-Hans";
  return undefined;
}
export function initialLocale(
  url: URL,
  embedded: boolean,
  saved: string | null,
  language: string,
): Locale {
  return (
    normalizeLocale(url.searchParams.get(localeParam)) ||
    (!embedded && normalizeLocale(saved)) ||
    normalizeLocale(language) ||
    "en"
  );
}
export function text(
  resource: Resource | undefined,
  key: string,
  original: string,
): string {
  const descriptor = resource?.fields.find((field) => field.key === key);
  // A native unsaved edit must never be overwritten by an older catalog entry.
  return descriptor?.source === original
    ? resource?.translations[key]?.text || original
    : original;
}
export function category(
  resource: Resource | undefined,
  column: string,
  value: Scalar,
): string | undefined {
  const field = resource?.fields.find(
    (item) => item.kind === "category" && item.target === column,
  );
  return (
    field &&
    resource?.translations[field.key]?.dictionary.find((item) =>
      Object.is(item.value, value),
    )?.label
  );
}
export function label(
  resource: Resource | undefined,
  target: string,
  original: string,
): string {
  const field = resource?.fields.find(
    (item) =>
      item.target === target &&
      (item.key.endsWith("/label") ||
        item.key.startsWith("metric/") ||
        item.key.startsWith("column/")) &&
      item.kind !== "category" &&
      !item.key.endsWith("/description"),
  );
  return field ? resource?.translations[field.key]?.text || original : original;
}
