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
import { createElement, useContext } from "react";
import { SafeMarkdown } from "@superset-ui/core/components";
import { category, Scalar, text } from "./contracts";
export { ControlText, useControlMessages } from "./ControlMessages";
export {
  FilterDropdown,
  filterDropdownBlur,
  filterDropdownKeyDown,
} from "./FilterDropdown";
export {
  SearchInput as LocalizedTableSearchInput,
  SelectPageSize as LocalizedTablePageSize,
} from "./TableControls";
import {
  FieldContext,
  FilterContext,
  InstanceContext,
  useLocalization,
} from "./runtime";
/** Called only from a presentation component, never a query/filter reducer. */
export function useDisplayTitle(original: string): string {
  const runtime = useLocalization();
  const field = useContext(FieldContext);
  if (!field || !runtime?.bundle) return original;
  return (
    field.display ??
    text(
      runtime.bundle.resources[`${runtime.kind}/${runtime.uuid}`],
      field.key,
      original,
    )
  );
}
export function useFilterText(
  id: string,
  property: string,
  original: string,
): string {
  const runtime = useLocalization();
  return text(
    runtime?.bundle?.resources[`dashboard/${runtime.uuid}`],
    `filter/${id}/${property}`,
    original,
  );
}
export function useFilterDisplay() {
  const runtime = useLocalization();
  const filter = useContext(FilterContext);
  const resource = filter?.datasetUuid
    ? runtime?.bundle?.resources[`dataset/${filter.datasetUuid}`]
    : undefined;
  return {
    revision: runtime?.bundle,
    label: (value: Scalar, original: string) =>
      category(resource, filter?.column || "", value) || original,
  };
}

/** Localize the displayed description without replacing editable native metadata. */
export function useChartDescription(id: number | undefined, original: string) {
  const runtime = useLocalization();
  const instance = useContext(InstanceContext);
  const binding = runtime?.bundle?.charts[String(id)];
  const chartUuid = runtime?.kind === "chart" ? runtime.uuid : binding?.uuid;
  const chart = runtime?.bundle?.resources[`chart/${chartUuid}`];
  const dashboard = runtime?.bundle?.resources[`dashboard/${runtime?.uuid}`];
  const chartText = text(chart, "description", original);
  const instanceKey = `layout/${instance}/chart/description`;
  const instanceText = text(dashboard, instanceKey, original);
  const instanceConfigured =
    dashboard?.fields.find((field) => field.key === instanceKey)?.source ===
      original && !!dashboard?.translations[instanceKey]?.text;
  const display = instanceConfigured ? instanceText : chartText;
  return {
    text: display,
    translated: display !== original,
    node: createElement(SafeMarkdown, { source: display }),
  };
}
