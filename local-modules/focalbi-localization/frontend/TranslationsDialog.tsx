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
import { useEffect, useState } from "react";
import { SupersetClient } from "@superset-ui/core";
import { Button, Input, Modal, Space } from "@superset-ui/core/components";
import { Alert } from "@apache-superset/core/components";
import { apiRoot, Catalog, Entry, locales, ResourceType } from "./contracts";
export interface DialogProps {
  kind: ResourceType;
  uuid: string;
  onClose: () => void;
  onSaved: () => void;
}
function errorMessage(error: unknown): string {
  const item = error as {
    message?: string;
    statusText?: string;
    response?: { json?: { message?: string } };
  };
  return (
    item.response?.json?.message ||
    item.message ||
    item.statusText ||
    "Could not save translations. Your edits remain available."
  );
}
export default function TranslationsDialog({
  kind,
  uuid,
  onClose,
  onSaved,
}: DialogProps) {
  const [catalog, setCatalog] = useState<Catalog>();
  const [entries, setEntries] = useState<Record<string, Entry>>({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [saving, setSaving] = useState(false);
  const [dictionaryDrafts, setDictionaryDrafts] = useState<
    Record<string, string>
  >({});
  const [remap, setRemap] = useState("{}");
  useEffect(() => {
    let active = true;
    SupersetClient.get({ endpoint: `${apiRoot}/resource/${kind}/${uuid}` })
      .then((response) => {
        if (!active) return;
        const value = response.json.result as Catalog;
        setCatalog(value);
        const known = new Set(value.fields.map((field) => field.key));
        setEntries(
          Object.fromEntries(
            Object.entries(value.entries).filter(([key]) => known.has(key)),
          ),
        );
        if (Object.keys(value.entries).some((key) => !known.has(key)))
          setNotice(
            "Removed fields are omitted from the next save. Export the catalog before saving if you need their historical entries.",
          );
      })
      .catch((error) => {
        if (active) setError(errorMessage(error));
      });
    return () => {
      active = false;
    };
  }, [kind, uuid]);
  async function save() {
    if (!catalog) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const next = { ...entries };
      for (const [key, draft] of Object.entries(dictionaryDrafts)) {
        const field = catalog.fields.find((item) => item.key === key)!;
        next[key] = {
          sourceHash: field.sourceHash,
          values: {},
          ...next[key],
          dictionary: JSON.parse(draft),
        };
      }
      const response = await SupersetClient.put({
        endpoint: `${apiRoot}/resource/${kind}/${uuid}`,
        jsonPayload: { revision: catalog.revision, entries: next },
      });
      setCatalog({
        ...catalog,
        revision: response.json.result.revision,
        entries: next,
      });
      setEntries(next);
      setNotice(
        "Translations saved. Native resource changes are saved separately.",
      );
      onSaved();
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }
  function download() {
    if (!catalog) return;
    const data = {
      version: 1,
      resources: [
        {
          type: kind,
          uuid,
          revision: catalog.revision,
          entries: catalog.entries,
        },
      ],
      remap: {},
      fieldRemap: {},
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `translations-${kind}-${uuid}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }
  async function importFile(file?: File) {
    if (!file || !catalog) return;
    setError("");
    try {
      const payload = JSON.parse(await file.text());
      const mapping = JSON.parse(remap);
      if (
        payload.version !== 1 ||
        !Array.isArray(payload.resources) ||
        !mapping ||
        typeof mapping !== "object" ||
        Array.isArray(mapping)
      )
        throw new Error(
          "Use a version 1 translation bundle and an object UUID mapping.",
        );
      const item = payload.resources?.find(
        (resource: { type: string; uuid: string }) =>
          resource.type === kind &&
          (mapping[resource.uuid] ||
            payload.remap?.[resource.uuid] ||
            resource.uuid) === uuid,
      );
      if (!item)
        throw new Error(
          "No resource maps to this editor. Supply an explicit source UUID → target UUID mapping.",
        );
      const fieldMapping = payload.fieldRemap?.[`${kind}/${uuid}`] || {};
      if (
        !item.entries ||
        typeof item.entries !== "object" ||
        Array.isArray(item.entries) ||
        typeof fieldMapping !== "object" ||
        Array.isArray(fieldMapping)
      )
        throw new Error("Entries and field mappings must be objects.");
      const imported: Record<string, Entry> = Object.fromEntries(
        Object.entries(item.entries).map(([key, value]) => [
          fieldMapping[key] || key,
          value as Entry,
        ]),
      );
      if (Object.keys(imported).length !== Object.keys(item.entries).length)
        throw new Error("Field mapping contains duplicate targets.");
      const known = new Set(catalog.fields.map((field) => field.key));
      if (Object.keys(imported).some((key) => !known.has(key)))
        throw new Error(
          "Imported field keys do not match. Supply fieldRemap in the bundle.",
        );
      setEntries(imported);
      setDictionaryDrafts({});
      setNotice(
        "Bundle loaded into the draft. Review changed originals and use Save translations to validate and commit.",
      );
    } catch (error) {
      setError(errorMessage(error));
    }
  }
  return (
    <Modal
      show
      onHide={onClose}
      title={`Translations — ${kind}`}
      maxWidth="large"
      footer={
        <Space>
          <Button onClick={onClose}>Close</Button>
          <Button
            buttonStyle="primary"
            disabled={!catalog || saving}
            onClick={save}
          >
            {saving ? "Saving…" : "Save translations"}
          </Button>
        </Space>
      }
    >
      {error && <Alert type="error" message={error} />}
      {notice && <Alert type="info" message={notice} />}
      <p>
        Original Superset text is preserved. Blank translations fall back to
        original text. Internal labels are supported for:{" "}
        {catalog?.supportedVizTypes.join(", ")}.
      </p>
      {!!catalog?.unsupportedVisualizations?.length && (
        <Alert
          type="info"
          message={
            "Internal label adapters unavailable for: " +
            catalog.unsupportedVisualizations
              .map((item) => `${item.title} (${item.type})`)
              .join(", ") +
            ". Shared titles and descriptions remain supported; internal fields retain native text."
          }
        />
      )}
      <Input
        aria-label="Search translation fields"
        placeholder="Search fields"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <div style={{ maxHeight: "55vh", overflow: "auto" }}>
        {catalog?.fields
          .filter((field) =>
            `${field.label} ${field.source}`
              .toLowerCase()
              .includes(search.toLowerCase()),
          )
          .map((field) => {
            const entry = entries[field.key];
            const stale = entry && entry.sourceHash !== field.sourceHash;
            return (
              <fieldset key={field.key} style={{ margin: "12px 0" }}>
                <legend>{field.label}</legend>
                <p>Original: {field.source || "(empty)"}</p>
                {stale && (
                  <Alert
                    type="warning"
                    message="Original changed. Review translations before restoring them."
                    action={
                      <Button
                        onClick={() =>
                          setEntries((current) => ({
                            ...current,
                            [field.key]: {
                              ...entry,
                              sourceHash: field.sourceHash,
                            },
                          }))
                        }
                      >
                        Mark reviewed
                      </Button>
                    }
                  />
                )}
                {field.kind === "category" ? (
                  <>
                    <p>
                      Authored category metadata only. Use raw values unchanged,
                      for example [
                      {
                        '{"value":"Source value","values":{"zh-Hant":"顯示文字","zh-Hans":"显示文字"}}'
                      }
                      ].
                    </p>
                    <Input.TextArea
                      aria-label={field.label + " dictionary"}
                      autoSize={{ minRows: 2, maxRows: 8 }}
                      value={
                        dictionaryDrafts[field.key] ??
                        JSON.stringify(entry?.dictionary || [], null, 2)
                      }
                      onChange={(event) =>
                        setDictionaryDrafts((current) => ({
                          ...current,
                          [field.key]: event.target.value,
                        }))
                      }
                    />
                  </>
                ) : (
                  locales.map((locale) => (
                    <div key={locale}>
                      <label>{locale}</label>
                      <Input.TextArea
                        aria-label={`${field.label} ${locale}`}
                        autoSize={{ minRows: 1, maxRows: 6 }}
                        value={entry?.values[locale] || ""}
                        onChange={(event) =>
                          setEntries((current) => ({
                            ...current,
                            [field.key]: {
                              sourceHash: field.sourceHash,
                              dictionary: [],
                              ...current[field.key],
                              values: {
                                ...current[field.key]?.values,
                                [locale]: event.target.value,
                              },
                            },
                          }))
                        }
                      />
                    </div>
                  ))
                )}
              </fieldset>
            );
          })}
      </div>
      <Space direction="vertical">
        <Button onClick={download} disabled={!catalog}>
          Export saved translations
        </Button>
        <label>
          Import UUID mapping (JSON)
          <Input
            aria-label="Import UUID mapping"
            value={remap}
            onChange={(event) => setRemap(event.target.value)}
          />
        </label>
        <label>
          Import translation bundle
          <input
            type="file"
            accept="application/json,.json"
            onChange={(event) => {
              void importFile(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </label>
      </Space>
    </Modal>
  );
}
