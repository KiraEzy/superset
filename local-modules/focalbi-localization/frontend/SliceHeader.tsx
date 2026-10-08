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
import { ComponentProps, forwardRef, useRef } from "react";
import { useSelector } from "react-redux";
import Host from "focalbi-host/SliceHeader";
import type { RootState } from "src/dashboard/types";
import { FieldContext, useLocalization } from "./runtime";
import { category, text } from "./contracts";
type Props = ComponentProps<typeof Host>;
const SliceHeader = forwardRef<HTMLDivElement, Props>((props, ref) => {
  const runtime = useLocalization();
  const item = useSelector(
    (state: RootState) => state.dashboardLayout.present[props.componentId],
  );
  const filters = useSelector(
    (state: RootState) => state.nativeFilters.filters,
  );
  const chart = useSelector(
    (state: RootState) => state.charts[props.slice.slice_id],
  );
  const applied = useRef<unknown[]>([]);
  const bundle = runtime?.bundle;
  const binding = bundle?.charts[String(props.slice.slice_id)];
  const resource = binding && bundle?.resources[`chart/${binding.uuid}`];
  const dashboard = bundle?.resources[`dashboard/${bundle.uuid}`];
  const original = props.sliceName || "";
  const instanceTitle =
    dashboard?.translations[`layout/${props.componentId}/chart/title`]?.text;
  let display = instanceTitle
    ? text(dashboard, `layout/${props.componentId}/chart/title`, original)
    : text(resource, "title", original);
  const settings = item?.meta.focalbi_rendering as
    | { title?: { filterId: string; single: string; multiple: string } }
    | undefined;
  const title = settings?.title;
  const filter = title && filters[title.filterId];
  if (
    title &&
    filter &&
    "targets" in filter &&
    "chartsInScope" in filter &&
    filter.chartsInScope?.includes(props.slice.slice_id)
  ) {
    const column = filter.targets[0]?.column?.name;
    const query = chart?.latestQueryFormData as
      | {
          extra_form_data?: {
            filters?: { col: unknown; op: string; val: unknown }[];
          };
        }
      | undefined;
    if (chart && ["success", "rendered"].includes(chart.chartStatus)) {
      const selected = query?.extra_form_data?.filters?.find(
        (item) => item.col === column && item.op === "IN",
      )?.val;
      applied.current = Array.isArray(selected) ? selected : [];
    }
    if (applied.current.length === 1) {
      const dataset =
        binding?.datasetUuid &&
        bundle?.resources[`dataset/${binding.datasetUuid}`];
      const raw = applied.current[0];
      const name =
        typeof raw === "string"
          ? category(dataset || undefined, column || "", raw) || raw
          : String(raw);
      display = text(
        dashboard,
        `layout/${props.componentId}/title/single`,
        title.single,
      ).replaceAll("{selection}", name);
    } else if (applied.current.length > 1)
      display = text(
        dashboard,
        `layout/${props.componentId}/title/multiple`,
        title.multiple,
      );
  }
  return (
    <FieldContext.Provider
      value={props.editMode ? null : { key: "title", display }}
    >
      <Host {...props} ref={ref} />
    </FieldContext.Provider>
  );
});
export default SliceHeader;
