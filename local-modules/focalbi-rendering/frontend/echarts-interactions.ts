/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { getInstanceByDom, EChartsType } from "echarts/core";
import type { Interaction, NativeInteraction } from "./contracts";

/** Bridge native renderer events into the shared viewer store. Baseline renderers
 * do not all expose legend/zoom callbacks; their source remains unchanged. */
export function observeEchartsInteractions(
  element: HTMLElement,
  state: () => Interaction,
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
        const saved = state().native;
        let pendingRestore = Boolean(saved);
        // Native Echart initializes its instance before its first full setOption.
        // Restore after that draw so notMerge cannot erase restored selections.
        const restore = () => {
          if (!pendingRestore || instance.isDisposed()) return;
          const options = instance.getOption();
          if (!options?.series) return;
          pendingRestore = false;
          if (saved?.legends?.length)
            instance.setOption({ legend: saved.legends }, { silent: true });
          if (saved?.zoom?.length)
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
        };
        const capture = () => {
          if (pendingRestore) return;
          const options = instance.getOption() as {
            legend?: NativeInteraction["legends"];
            dataZoom?: NativeInteraction["zoom"];
          } | undefined;
          if (!options) return;
          state().native = {
            legends: options.legend?.map((legend) => ({
              selected: { ...legend.selected },
              scrollDataIndex: legend.scrollDataIndex,
            })),
            zoom: options.dataZoom?.map((zoom) => ({
              start: zoom.start,
              end: zoom.end,
            })),
          };
        };
        events.forEach((event) => instance.on(event, capture));
        instance.on("finished", restore);
        restore();
        bindings.set(instance, () => {
          if (!instance.isDisposed()) {
            events.forEach((event) => instance.off(event, capture));
            instance.off("finished", restore);
          }
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
