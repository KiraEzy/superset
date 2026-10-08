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
import {
  ComponentProps,
  forwardRef,
  useCallback,
  useContext,
  useEffect,
  useRef,
} from "react";
import NativeCore from "focalbi-native/SuperChartCore";
import Host from "focalbi-host/SuperChartCore";
import {
  InstanceContext,
  NativeQueryContext,
  useLocalization,
} from "./runtime";
import { localizeProps, presentation } from "./presentation";
import { DisplayState, observeDisplayState } from "./EchartState";
import { retainDisplayProps, sameResultData } from "./displayState";
import { t } from "@apache-superset/core/translation";
type Props = ComponentProps<typeof Host>;
const SuperChartCore = forwardRef<NativeCore, Props>((props, ref) => {
  const runtime = useLocalization();
  const instance = useContext(InstanceContext);
  const form = props.chartProps?.rawFormData;
  const core = useRef<NativeCore | null>(null);
  const retainRef = useCallback(
    (value: NativeCore | null) => {
      core.current = value;
      if (typeof ref === "function") ref(value);
      else if (ref) ref.current = value;
    },
    [ref],
  );
  const displayState = useRef<DisplayState>({});
  const data = props.chartProps?.queriesData.map((result) => result.data) || [];
  const query = useRef(data);
  if (!sameResultData(query.current, data)) {
    query.current = data;
    displayState.current = {};
  }
  useEffect(
    () =>
      core.current?.container
        ? observeDisplayState(
            core.current.container,
            () => displayState.current,
          )
        : undefined,
    [props.chartProps],
  );
  const id = String(form?.slice_id || "");
  const dimensions = [
    ...new Set([
      ...(Array.isArray(form?.groupby)
        ? form.groupby.filter(
            (column): column is string => typeof column === "string",
          )
        : []),
      ...(typeof form?.x_axis === "string" ? [form.x_axis] : []),
    ]),
  ];
  const post = useCallback(
    (transformed: Record<string, unknown>) => {
      const context = presentation(runtime?.bundle, id, instance, dimensions);
      context.locale = runtime?.locale;
      context.nativeTotalTemplate = t("Total: %s", "{value}");
      context.sourceControls = form;
      const existing = props.postTransformProps
        ? props.postTransformProps(transformed)
        : transformed;
      return retainDisplayProps(
        localizeProps(props.chartType || "", existing, context),
        displayState.current,
      );
    },
    [
      runtime?.bundle,
      runtime?.locale,
      id,
      instance,
      props.postTransformProps,
      props.chartType,
      form,
    ],
  );
  return (
    <NativeQueryContext.Provider value={query.current}>
      <Host {...props} ref={retainRef} postTransformProps={post} />
    </NativeQueryContext.Provider>
  );
});
export default SuperChartCore;
