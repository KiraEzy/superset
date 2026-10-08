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
import { ComponentType, lazy, Suspense, useState } from "react";
import { Button } from "@superset-ui/core/components";
import { Alert } from "@apache-superset/core/components";
import type { DialogProps } from "./TranslationsDialog";
import { ResourceType } from "./contracts";
declare const __webpack_init_sharing__: (scope: string) => Promise<void>;
declare const __webpack_share_scopes__: { default: unknown };
interface Container {
  init: (scope: unknown) => Promise<void>;
  get: (name: string) => Promise<() => { default: ComponentType<DialogProps> }>;
}
declare global {
  interface Window {
    focalbi_contentLocalization?: Container;
  }
}
let loader: Promise<{ default: ComponentType<DialogProps> }> | undefined;
async function loadDialog() {
  if (!loader)
    loader = (async () => {
      if (!window.focalbi_contentLocalization)
        await new Promise<void>((resolve, reject) => {
          const script = document.createElement("script");
          script.src =
            "/api/v1/extensions/focalbi/content-localization/remoteEntry.js";
          script.onload = () => resolve();
          script.onerror = () =>
            reject(
              new Error("Translation editor extension could not be loaded"),
            );
          document.head.appendChild(script);
        });
      await __webpack_init_sharing__("default");
      const container = window.focalbi_contentLocalization!;
      await container.init(__webpack_share_scopes__.default);
      return (await container.get("./Dialog"))();
    })().catch((error) => {
      loader = undefined;
      throw error;
    });
  return loader;
}
export function TranslationButton({
  kind,
  uuid,
  onSaved,
}: {
  kind: ResourceType;
  uuid: string;
  onSaved: () => void;
}) {
  const [Dialog, setDialog] = useState<ComponentType<DialogProps>>();
  const [error, setError] = useState("");
  return (
    <>
      <Button
        data-test="focalbi-translations"
        onClick={() => {
          setError("");
          loadDialog()
            .then((module) => setDialog(() => module.default))
            .catch((error) => setError(error.message));
        }}
      >
        Translations
      </Button>
      {error && <Alert type="error" message={error} />}
      {Dialog && (
        <Suspense fallback="Loading translation editor…">
          <Dialog
            kind={kind}
            uuid={uuid}
            onClose={() => setDialog(undefined)}
            onSaved={onSaved}
          />
        </Suspense>
      )}
    </>
  );
}
