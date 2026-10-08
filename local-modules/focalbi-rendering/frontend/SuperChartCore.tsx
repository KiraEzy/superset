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
import { forwardRef, useCallback, useContext } from "react";
import NativeCore, { Props } from "focalbi-native/SuperChartCore";
import {
  Behavior,
  ChartProps,
  getChartMetadataRegistry,
} from "@superset-ui/core";
import { RendererContext } from "./context";
import { registry, renderKey } from "./registry";
export type { Props } from "focalbi-native/SuperChartCore";

/** Dispatch only after native query results arrive; Explore retains native rendering. */
const SuperChartCore = forwardRef<NativeCore, Props>((props, ref) => {
  const engine = useContext(RendererContext);
  const nativeFilter = getChartMetadataRegistry()
    .get(props.chartType)
    ?.behaviors.includes(Behavior.NativeFilter);
  // Keep the loadable renderer identity stable when a display transform changes.
  // Native postTransformProps updates its envelope without remounting the chart.
  const envelope = useCallback((raw: ChartProps) => ({ raw }), []);
  const compose = useCallback(
    (value: { raw: ChartProps }) => ({ ...value, post: props.postTransformProps }),
    [props.postTransformProps],
  );
  if (!engine || !registry[props.chartType] || props.overrideTransformProps) {
    return (
      <>
        {engine === "fork" && !registry[props.chartType] && !nativeFilter && (
          <span data-test="focalbi-native-fallback">
            Native renderer: {props.chartType}
          </span>
        )}
        <NativeCore {...props} ref={ref} />
      </>
    );
  }
  return (
    <NativeCore
      {...props}
      ref={ref}
      chartType={renderKey(props.chartType)}
      overrideTransformProps={envelope}
      postTransformProps={compose}
    />
  );
});
export default SuperChartCore;
