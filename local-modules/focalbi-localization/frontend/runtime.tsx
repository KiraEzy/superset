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
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  ReactNode,
} from "react";
import { SupersetClient } from "@superset-ui/core";
import { Select, Space } from "@superset-ui/core/components";
import { Alert } from "@apache-superset/core/components";
import {
  apiRoot,
  bridgeType,
  bridgeVersion,
  Bundle,
  initialLocale,
  Locale,
  localeParam,
  normalizeLocale,
  ResourceType,
} from "./contracts";
import { TranslationButton } from "./TranslationButton";

interface Runtime {
  locale: Locale;
  bundle?: Bundle;
  uuid?: string;
  editable: boolean;
  kind: ResourceType;
  refresh: () => void;
}
export const LocalizationContext = createContext<Runtime | null>(null);
export const FieldContext = createContext<{
  key: string;
  display?: string;
} | null>(null);
export const InstanceContext = createContext<string | undefined>(undefined);
export const NativeQueryContext = createContext<unknown>(undefined);
export const FilterContext = createContext<{
  datasetUuid?: string;
  column?: string;
} | null>(null);
export const useLocalization = () => useContext(LocalizationContext);
export async function getResult<T>(endpoint: string): Promise<T> {
  const response = await SupersetClient.get({ endpoint });
  return response.json.result as T;
}
const preference = "focalbi.content-locale";

export function Provider({
  kind,
  id,
  children,
}: {
  kind: ResourceType;
  id?: number | string;
  children: ReactNode;
}) {
  const embedded = window.location.pathname.startsWith("/embedded/");
  const [locale, setLocale] = useState<Locale>(() => {
    let saved = null;
    try {
      saved = localStorage.getItem(preference);
    } catch {
      /* Optional preference. */
    }
    return initialLocale(
      new URL(window.location.href),
      embedded,
      saved,
      navigator.language,
    );
  });
  const [identity, setIdentity] = useState<{
    uuid: string;
    editable: boolean;
  }>();
  const [bundle, setBundle] = useState<Bundle>();
  const [failure, setFailure] = useState(false);
  const [revision, setRevision] = useState(0);
  const generation = useRef(0);
  const pendingAcknowledgement = useRef<{
    origin: string;
    locale: Locale;
    requestId: number;
  }>();
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let mounted = true;
    setIdentity(undefined);
    setBundle(undefined);
    setFailure(false);
    if (id)
      getResult<{ uuid: string; editable: boolean }>(
        `${apiRoot}/resolve/${kind}/${Number(id)}`,
      )
        .then((value) => {
          if (mounted) setIdentity(value);
        })
        .catch(() => {
          if (mounted) setFailure(true);
        });
    return () => {
      mounted = false;
    };
  }, [kind, id]);
  useEffect(() => {
    const ticket = ++generation.current;
    if (!identity) return;
    getResult<Bundle>(
      `${apiRoot}/bundle/${kind}/${identity.uuid}?locale=${locale}`,
    )
      .then((value) => {
        if (generation.current === ticket) {
          setBundle(value);
          setFailure(false);
        }
      })
      .catch(() => {
        if (generation.current === ticket) {
          setBundle(undefined);
          setFailure(true);
        }
      });
    return () => {
      ++generation.current;
    };
  }, [identity, kind, locale, revision]);
  const applyLocale = useCallback(
    (value: Locale, persist = false) => {
      setLocale(value);
      if (persist && !embedded) {
        try {
          localStorage.setItem(preference, value);
        } catch {
          /* Optional preference. */
        }
        const url = new URL(window.location.href);
        url.searchParams.set(localeParam, value);
        window.history.replaceState(window.history.state, "", url);
      }
    },
    [embedded],
  );
  useEffect(() => {
    if (!embedded || !bundle) return;
    const allowed = bundle.allowedOrigins.filter((origin) => {
      try {
        return new URL(origin).origin === origin;
      } catch {
        return false;
      }
    });
    const receive = (event: MessageEvent) => {
      if (event.source !== window.parent || !allowed.includes(event.origin))
        return;
      const data = event.data;
      if (data?.type !== bridgeType || data.version !== bridgeVersion) return;
      const next = normalizeLocale(data.locale);
      if (data.action === "hello")
        window.parent.postMessage(
          { type: bridgeType, version: bridgeVersion, action: "ready", locale },
          event.origin,
        );
      if (data.action === "set" && next) {
        if (!Number.isSafeInteger(data.requestId)) return;
        pendingAcknowledgement.current = {
          origin: event.origin,
          locale: next,
          requestId: data.requestId,
        };
        applyLocale(next);
        if (bundle.locale === next) {
          window.parent.postMessage(
            {
              type: bridgeType,
              version: bridgeVersion,
              action: "ack",
              locale: next,
              requestId: data.requestId,
            },
            event.origin,
          );
          pendingAcknowledgement.current = undefined;
        }
      }
    };
    window.addEventListener("message", receive);
    for (const origin of allowed)
      window.parent.postMessage(
        { type: bridgeType, version: bridgeVersion, action: "ready", locale },
        origin,
      );
    return () => window.removeEventListener("message", receive);
  }, [embedded, bundle, locale, applyLocale]);
  useEffect(() => {
    const pending = pendingAcknowledgement.current;
    if (
      pending &&
      bundle?.locale === pending.locale &&
      locale === pending.locale
    ) {
      window.parent.postMessage(
        {
          type: bridgeType,
          version: bridgeVersion,
          action: "ack",
          locale,
          requestId: pending.requestId,
        },
        pending.origin,
      );
      pendingAcknowledgement.current = undefined;
    }
  }, [bundle, locale]);
  const current = bundle?.locale === locale ? bundle : undefined;
  const selectorId = `focalbi-content-language-${kind}-${id || "preview"}`;
  return (
    <LocalizationContext.Provider
      value={{
        locale,
        bundle: current,
        uuid: identity?.uuid,
        editable: identity?.editable || false,
        kind,
        refresh,
      }}
    >
      <Space data-test="focalbi-localization-toolbar">
        {!embedded && kind !== "dataset" && (
          <>
            <label htmlFor={selectorId}>Content language</label>
            <Select
              id={selectorId}
              value={locale}
              options={[
                { value: "en", label: "English" },
                { value: "zh-Hant", label: "繁體中文" },
                { value: "zh-Hans", label: "简体中文" },
              ]}
              onChange={(value: Locale) => applyLocale(value, true)}
            />
          </>
        )}
        {identity?.editable && (
          <TranslationButton
            kind={kind}
            uuid={identity.uuid}
            onSaved={refresh}
          />
        )}
      </Space>
      {failure && !embedded && (
        <Alert
          type="warning"
          message="Translations unavailable. Original content is displayed."
        />
      )}
      {children}
    </LocalizationContext.Provider>
  );
}
