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
import { ComponentProps, useState } from "react";
import NativeBuilder from "focalbi-native/DashboardBuilder";
import { Select, Space } from "@superset-ui/core/components";
import { RendererContext } from "./context";
import type { Engine } from "./settings";

/** Add presentation controls around the original builder, including SDK embeds. */
export default function DashboardBuilder(
  props: ComponentProps<typeof NativeBuilder>,
) {
  const [showRendererSelector] = useState(() => {
    try {
      return localStorage.getItem("focalbi.rendererSelector") === "true";
    } catch {
      return false;
    }
  });
  const [engine, setEngine] = useState<Engine>(() => {
    if (!showRendererSelector) return "fork";
    try {
      return localStorage.getItem("focalbi.renderer") === "baseline"
        ? "baseline"
        : "fork";
    } catch {
      return "fork";
    }
  });
  return (
    <RendererContext.Provider value={engine}>
      {showRendererSelector && (
        <Space
          style={{ padding: "8px 16px" }}
          data-test="focalbi-renderer-toolbar"
        >
          <label htmlFor="focalbi-renderer">Renderer</label>
          <Select
            id="focalbi-renderer"
            aria-label="Renderer"
            value={engine}
            style={{ width: 190 }}
            options={[
              { value: "baseline", label: "Superset baseline" },
              { value: "fork", label: "FocalBI fork" },
            ]}
            onChange={(value: Engine) => {
              setEngine(value);
              try {
                localStorage.setItem("focalbi.renderer", value);
              } catch {
                /* Storage is optional. */
              }
            }}
          />
        </Space>
      )}
      <NativeBuilder {...props} />
    </RendererContext.Provider>
  );
}
