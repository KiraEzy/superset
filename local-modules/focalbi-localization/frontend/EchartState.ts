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
import { EChartsType, getInstanceByDom } from "echarts/core";
import {
  DisplayOptions,
  DisplayState,
  needsDisplayRestore,
} from "./displayState";
export type { DisplayState } from "./displayState";
/** Retain raw interaction keys across display redraws, without altering queries. */
export function observeDisplayState(
  element: HTMLElement,
  state: () => DisplayState,
): () => void {
  const bindings = new Map<EChartsType, () => void>();
  const events = [
    "legendselectchanged",
    "legendselected",
    "legendunselected",
    "legendselectall",
    "legendinverseselect",
    "legendscroll",
    "datazoom",
  ];
  const bind = () => {
    element
      .querySelectorAll<HTMLElement>("[_echarts_instance_]")
      .forEach((node) => {
        const instance = getInstanceByDom(node);
        if (!instance || instance.isDisposed() || bindings.has(instance))
          return;
        let restoring = false;
        const restore = () => {
          if (restoring || instance.isDisposed()) return;
          const options = (instance.getOption() || {}) as DisplayOptions;
          const saved = state();
          if (!options.series || !needsDisplayRestore(options, saved)) return;
          restoring = true;
          try {
            if (saved.legends?.length)
              instance.setOption({ legend: saved.legends }, { silent: true });
            if (saved.zoom?.length)
              instance.dispatchAction(
                {
                  type: "dataZoom",
                  batch: saved.zoom.map((value, dataZoomIndex) => ({
                    ...value,
                    dataZoomIndex,
                  })),
                },
                { silent: true },
              );
          } finally {
            restoring = false;
          }
        };
        const capture = () => {
          if (restoring) return;
          const options = (instance.getOption() || {}) as DisplayOptions;
          if (!options.series) return;
          const saved = state();
          saved.legends = options.legend?.map((value) => ({
            selected: { ...value.selected },
            scrollDataIndex: value.scrollDataIndex,
          }));
          saved.zoom = options.dataZoom?.map((value) => ({
            start: value.start,
            end: value.end,
          }));
        };
        events.forEach((event) => instance.on(event, capture));
        // Native Echart uses notMerge for a display update. Restore after each draw,
        // including an existing instance; comparison prevents recursive redraws.
        instance.on("finished", restore);
        restore();
        bindings.set(instance, () => {
          if (instance.isDisposed()) return;
          events.forEach((event) => instance.off(event, capture));
          instance.off("finished", restore);
        });
      });
  };
  const observer = new MutationObserver(bind);
  observer.observe(element, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["_echarts_instance_"],
  });
  bind();
  return () => {
    observer.disconnect();
    bindings.forEach((cleanup) => cleanup());
  };
}
