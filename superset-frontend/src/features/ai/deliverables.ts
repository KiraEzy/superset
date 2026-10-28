/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The ASF licenses this file to You under the Apache License, Version 2.0
 * (the "License"); you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing, software distributed
 * under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
 * CONDITIONS OF ANY KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations under the License.
 */
import { Artifact } from './runtime';
import { rewriteSupersetExploreUrl } from './supersetUrlUtils';

export interface Deliverable {
  key: string;
  artifact: Artifact;
  title: string;
  url?: string;
}

const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

function identifier(value: unknown): string | undefined {
  if (typeof value === 'number' && Number.isSafeInteger(value) && value > 0)
    return String(value);
  if (
    typeof value === 'string' &&
    (/^[1-9]\d*$/.test(value) ||
      /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i.test(value))
  )
    return value.toLowerCase();
  return undefined;
}

function resource(artifact: Artifact) {
  if (!['chart', 'dashboard'].includes(artifact.type)) return undefined;
  const payload = record(artifact.payload[artifact.type] ?? artifact.payload);
  const id = identifier(
    artifact.type === 'chart'
      ? (payload.slice_id ?? payload.id ?? payload.uuid)
      : (payload.id ?? payload.uuid),
  );
  const connection = artifact.provenance?.connection_id;
  // Missing scope cannot safely be merged with another resource or connection.
  if (!id || typeof connection !== 'string' || !connection) return undefined;
  return { key: JSON.stringify([connection, artifact.type, id]), id, payload };
}

function safeUrl(value: unknown): string | undefined {
  if (
    typeof value !== 'string' ||
    /[\s\\]/.test(value) ||
    Array.from(value).some(character => character.charCodeAt(0) < 32)
  )
    return undefined;
  if (/^\/(?!\/)/.test(value)) return value;
  try {
    const url = new URL(value);
    if (
      ['http:', 'https:'].includes(url.protocol) &&
      !url.username &&
      !url.password
    )
      return value;
  } catch {
    // Invalid URLs stay inspectable as evidence, never executable links.
  }
  return undefined;
}

function sameCall(left: Artifact, right: Artifact): boolean {
  return (
    typeof left.provenance?.call_id === 'string' &&
    left.provenance.call_id === right.provenance?.call_id &&
    left.provenance.connection_id === right.provenance?.connection_id
  );
}

function unsavedPreview(artifact: Artifact): boolean {
  return Boolean(
    artifact.payload.form_data_key &&
    (!artifact.saved || artifact.payload.saved === false),
  );
}

/** Derive a compact display without changing the authoritative artifacts. */
export function groupDeliverables(artifacts: Artifact[]): {
  deliverables: Deliverable[];
  details: Artifact[];
} {
  const resources = new Map<string, Deliverable>();
  const associatedSources = new Set<string>();
  artifacts.forEach(artifact => {
    const entity = resource(artifact);
    if (!entity || !artifact.saved || unsavedPreview(artifact)) return;
    resources.set(entity.key, {
      key: entity.key,
      artifact,
      title: artifact.title,
    });
  });
  artifacts.forEach(artifact => {
    const entity = resource(artifact);
    const previous = entity && resources.get(entity.key);
    if (!entity || !previous) return;
    // A read refreshes a saved entity, but a modified preview must not replace it.
    if (unsavedPreview(artifact)) return;
    const sources = artifacts.filter(
      source =>
        source.type === 'source' &&
        sameCall(source, artifact) &&
        (artifact.type === 'dashboard'
          ? source.title === 'dashboard url'
          : ['explore url', 'chart url'].includes(source.title)),
    );
    const rawUrl =
      safeUrl(entity.payload[`${artifact.type}_url`]) ??
      safeUrl(entity.payload.explore_url) ??
      safeUrl(entity.payload.url) ??
      sources.map(source => safeUrl(source.payload.url)).find(Boolean);
    const native =
      artifact.provenance?.connection_id === 'focalbi' ||
      String(artifact.provenance?.tool ?? '').startsWith('focalbi__');
    const fallback =
      native && (artifact.type === 'dashboard' || /^\d+$/.test(entity.id))
        ? artifact.type === 'dashboard'
          ? `/superset/dashboard/${entity.id}/`
          : `/explore/?slice_id=${entity.id}`
        : undefined;
    sources.forEach(source => {
      if (safeUrl(source.payload.url)) associatedSources.add(source.id);
    });
    resources.set(entity.key, {
      ...previous,
      artifact,
      title:
        artifact.title && artifact.title !== 'Chart preview'
          ? artifact.title
          : previous.title,
      url:
        fallback ??
        (rawUrl
          ? native
            ? rewriteSupersetExploreUrl(rawUrl)
            : rawUrl
          : previous.url),
    });
  });
  const deliverables = [...resources.values()].sort(
    (left, right) =>
      Number(right.artifact.type === 'dashboard') -
      Number(left.artifact.type === 'dashboard'),
  );
  const visible = new Set(deliverables.map(item => item.artifact.id));
  return {
    deliverables,
    details: artifacts.filter(
      artifact =>
        !visible.has(artifact.id) && !associatedSources.has(artifact.id),
    ),
  };
}
