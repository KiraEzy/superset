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
  bridgeType,
  bridgeVersion,
  Locale,
  normalizeLocale,
} from "./contracts";
export interface LocaleBridge {
  setContentLocale: (locale: Locale) => void;
  destroy: () => void;
}
/** Attach to the SDK-created iframe. This does not replace or modify the SDK. */
export function createLocaleBridge(
  frame: HTMLIFrameElement,
  initial: Locale,
  onApplied?: (locale: Locale) => void,
): LocaleBridge {
  const origin = new URL(frame.src, window.location.href).origin;
  let locale = initial;
  let ready = false;
  let requestId = 0;
  const send = () => {
    if (ready)
      frame.contentWindow?.postMessage(
        {
          type: bridgeType,
          version: bridgeVersion,
          action: "set",
          locale,
          requestId: ++requestId,
        },
        origin,
      );
  };
  const receive = (event: MessageEvent) => {
    if (
      event.source !== frame.contentWindow ||
      event.origin !== origin ||
      event.data?.type !== bridgeType ||
      event.data.version !== bridgeVersion
    )
      return;
    if (event.data.action === "ready") {
      ready = true;
      send();
    }
    if (
      event.data.action === "ack" &&
      event.data.requestId === requestId &&
      event.data.locale === locale
    )
      onApplied?.(locale);
  };
  window.addEventListener("message", receive);
  const probe = window.setInterval(() => {
    if (!ready)
      frame.contentWindow?.postMessage(
        { type: bridgeType, version: bridgeVersion, action: "hello" },
        origin,
      );
  }, 1000);
  return {
    setContentLocale(value) {
      const next = normalizeLocale(value);
      if (!next) throw new Error("Unsupported content locale");
      locale = next;
      send();
    },
    destroy() {
      clearInterval(probe);
      window.removeEventListener("message", receive);
    },
  };
}
