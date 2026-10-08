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
export type FilterValue = string | number | boolean | null;
export interface FilterOption {
  value?: unknown;
  label?: unknown;
  disabled?: boolean;
  isNewOption?: boolean;
}

/** Preserve raw option identities, including false, zero, empty text and null. */
export function isFilterValue(value: unknown): value is FilterValue {
  return (
    value === null || ["string", "number", "boolean"].includes(typeof value)
  );
}

/** Select only loaded, enabled matches; never fetch or infer unseen source rows. */
export function filterActionValues(
  options: readonly FilterOption[],
  selected: readonly unknown[] | null | undefined,
  search: string,
) {
  const query = search.trim().toLowerCase();
  const current = (selected || []).filter(isFilterValue);
  const selectedSet = new Set(current);
  const additions = new Set<FilterValue>();
  for (const option of options) {
    if (option.disabled || option.isNewOption || !isFilterValue(option.value))
      continue;
    const matches =
      !query ||
      [option.label, option.value].some(
        (value) =>
          value !== undefined &&
          String(value).trim().toLowerCase().includes(query),
      );
    if (matches && !selectedSet.has(option.value)) additions.add(option.value);
  }
  return {
    current,
    additions: [...additions],
    all: [...current, ...additions],
  };
}
