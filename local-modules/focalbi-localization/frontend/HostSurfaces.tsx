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
import { ComponentProps } from "react";
import { useSelector } from "react-redux";
import NativeDashboardHeader from "focalbi-native/DashboardHeader";
import NativeExplore from "focalbi-native/Explore";
import NativeExploreHeader from "focalbi-native/ExploreHeader";
import NativeDataset from "focalbi-native/Dataset";
import NativeChart from "focalbi-native/Chart";
import NativeTab from "focalbi-native/Tab";
import NativeMarkdown from "focalbi-native/Markdown";
import NativeGridHeader from "focalbi-native/GridHeader";
import NativeFilter from "focalbi-native/FilterControl";
import {
  FilterContext,
  FieldContext,
  InstanceContext,
  Provider,
  useLocalization,
} from "./runtime";
import { text } from "./contracts";
export function DashboardHeader() {
  return (
    <FieldContext.Provider value={{ key: "title" }}>
      <NativeDashboardHeader />
    </FieldContext.Provider>
  );
}
export function Explore(props: ComponentProps<typeof NativeExplore>) {
  const id = useSelector(
    (state: {
      explore?: {
        slice?: { slice_id?: number };
        form_data?: { slice_id?: number };
      };
    }) => state.explore?.slice?.slice_id || state.explore?.form_data?.slice_id,
  );
  return (
    <Provider kind="chart" id={id}>
      <NativeExplore {...props} />
    </Provider>
  );
}
export function ExploreHeader(
  props: ComponentProps<typeof NativeExploreHeader>,
) {
  return (
    <FieldContext.Provider value={{ key: "title" }}>
      <NativeExploreHeader {...props} />
    </FieldContext.Provider>
  );
}
export function Dataset(props: ComponentProps<typeof NativeDataset>) {
  return (
    <Provider kind="dataset" id={props.datasource.id}>
      <NativeDataset {...props} />
    </Provider>
  );
}
export function Chart(props: ComponentProps<typeof NativeChart>) {
  return (
    <InstanceContext.Provider value={props.componentId}>
      <NativeChart {...props} />
    </InstanceContext.Provider>
  );
}
export function Tab(props: ComponentProps<typeof NativeTab>) {
  const runtime = useLocalization();
  const resource = runtime?.bundle?.resources[`dashboard/${runtime.uuid}`];
  const meta = props.component.meta;
  const component = props.editMode
    ? props.component
    : {
        ...props.component,
        meta: {
          ...meta,
          text: text(
            resource,
            `layout/${props.id}/text`,
            String(meta.text || ""),
          ),
        },
      };
  return <NativeTab {...props} component={component} />;
}
export const RENDER_TAB = "RENDER_TAB";
export const RENDER_TAB_CONTENT = "RENDER_TAB_CONTENT";
export function Markdown(props: ComponentProps<typeof NativeMarkdown>) {
  const runtime = useLocalization();
  const resource = runtime?.bundle?.resources[`dashboard/${runtime.uuid}`];
  const meta = props.component.meta;
  const component = props.editMode
    ? props.component
    : {
        ...props.component,
        meta: {
          ...meta,
          code: text(
            resource,
            `layout/${props.id}/code`,
            String(meta.code || ""),
          ),
        },
      };
  return <NativeMarkdown {...props} component={component} />;
}
export function GridHeader(props: ComponentProps<typeof NativeGridHeader>) {
  const runtime = useLocalization();
  const resource = runtime?.bundle?.resources[`dashboard/${runtime.uuid}`];
  const meta = props.component.meta;
  const component = props.editMode
    ? props.component
    : {
        ...props.component,
        meta: {
          ...meta,
          text: text(
            resource,
            `layout/${props.id}/text`,
            String(meta.text || ""),
          ),
        },
      };
  return <NativeGridHeader {...props} component={component} />;
}
export function FilterControl(props: ComponentProps<typeof NativeFilter>) {
  const runtime = useLocalization();
  const target =
    "targets" in props.filter ? props.filter.targets[0] : undefined;
  const datasetUuid =
    target?.datasetId && runtime?.bundle?.datasets[String(target.datasetId)];
  return (
    <FilterContext.Provider
      value={{
        datasetUuid: datasetUuid || undefined,
        column: target?.column?.name,
      }}
    >
      <NativeFilter {...props} />
    </FilterContext.Provider>
  );
}
