/**
 * Licensed to the Apache Software Foundation (ASF) under one or more
 * contributor license agreements. See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The ASF licenses this file to You under the Apache License, Version 2.0
 * (the "License"); you may not use this file except in compliance with
 * the License. You may obtain a copy of the License at
 * http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
import { ComponentProps, useContext } from "react";
import NativeDeckGL from "@deck.gl/react";
import { MapInteractionContext } from "./MapInteraction";

/** Lock opted-in camera gestures while preserving picking and native auto-fit. */
export default function DeckGL(props: ComponentProps<typeof NativeDeckGL>) {
  const { disableDrag, disableZoom } = useContext(MapInteractionContext);
  const controller = disableDrag && disableZoom ? false
    : (disableDrag || disableZoom) && props.controller
    ? { ...(typeof props.controller === "object" ? props.controller : {}),
        ...(disableDrag ? { dragPan: false, dragRotate: false, touchRotate: false } : {}),
        ...(disableZoom ? { scrollZoom: false, doubleClickZoom: false,
          touchZoom: false, keyboard: false } : {}) }
    : props.controller;
  return <NativeDeckGL {...props} controller={controller} />;
}
