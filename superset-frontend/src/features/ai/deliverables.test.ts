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
import { groupDeliverables } from './deliverables';

const fixtureArtifact = (
  id: string,
  overrides: Partial<Artifact> = {},
): Artifact => ({
  id,
  type: 'chart',
  title: `Chart ${id}`,
  payload: { slice_id: 12 },
  saved: true,
  version: 1,
  provenance: { connection_id: 'focalbi', call_id: id },
  ...overrides,
});

test('keeps latest saved resource and related URLs while retaining intermediate evidence', () => {
  const original = fixtureArtifact('original');
  const latest = fixtureArtifact('latest', { title: 'Updated chart' });
  const source = fixtureArtifact('url', {
    type: 'source',
    title: 'explore url',
    payload: { url: '/explore/?slice_id=12' },
    provenance: latest.provenance,
  });
  const sql = fixtureArtifact('sql', {
    type: 'sql',
    payload: { sql: 'SELECT 1' },
  });
  const items = [original, latest, source, sql];
  const snapshot = JSON.stringify(items);
  const grouped = groupDeliverables(items);
  expect(grouped.deliverables).toHaveLength(1);
  expect(grouped.deliverables[0]).toMatchObject({
    artifact: latest,
    url: '/explore/?slice_id=12',
  });
  expect(grouped.details).toEqual([original, sql]);
  expect(JSON.stringify(items)).toBe(snapshot);
});

test('does not merge identical names, different connections or different resource types', () => {
  const items = [
    fixtureArtifact('one', { title: 'Same name' }),
    fixtureArtifact('two', { title: 'Same name', payload: { slice_id: 13 } }),
    fixtureArtifact('remote', { provenance: { connection_id: 'other' } }),
    fixtureArtifact('dashboard', { type: 'dashboard', payload: { id: 12 } }),
  ];
  const { deliverables } = groupDeliverables(items);
  expect(deliverables).toHaveLength(4);
  expect(deliverables[0].artifact.id).toBe('dashboard');
});

test('does not promote previews, writes without resource identity or missing scope', () => {
  const items = [
    fixtureArtifact('preview', {
      saved: false,
      payload: { form_data_key: 'preview' },
    }),
    fixtureArtifact('missing-id', { payload: { form_data: {} } }),
    fixtureArtifact('missing-scope', { provenance: {} }),
    fixtureArtifact('dataset', { type: 'dataset', payload: { id: 1 } }),
  ];
  expect(groupDeliverables(items)).toEqual({
    deliverables: [],
    details: items,
  });
});

test('updates saved entries from later reads but preserves them through unsaved edits', () => {
  const saved = fixtureArtifact('saved');
  const read = fixtureArtifact('read', { saved: false, title: 'Read title' });
  const preview = fixtureArtifact('preview', {
    saved: false,
    payload: { slice_id: 12, form_data_key: 'edit' },
  });
  const { deliverables, details } = groupDeliverables([saved, read, preview]);
  expect(deliverables[0].artifact).toBe(read);
  expect(details).toEqual([saved, preview]);
});

test('associates URLs only within the same call and connection and rejects unsafe links', () => {
  const resource = fixtureArtifact('remote', {
    provenance: { connection_id: 'remote', call_id: 'call' },
  });
  const source = fixtureArtifact('url', {
    type: 'source',
    title: 'chart url',
    payload: { url: 'https://example.com/chart/12' },
    provenance: resource.provenance,
  });
  expect(groupDeliverables([resource, source]).deliverables[0].url).toBe(
    'https://example.com/chart/12',
  );
  expect(
    groupDeliverables([
      resource,
      { ...source, provenance: { connection_id: 'other', call_id: 'call' } },
    ]).deliverables[0].url,
  ).toBeUndefined();
  [
    'javascript:alert(1)',
    '//example.com',
    '/\\example.com',
    'https://user:password@example.com',
    '/bad\nurl',
  ].forEach(url => {
    const unsafe = { ...source, payload: { url } };
    expect(
      groupDeliverables([resource, unsafe]).deliverables[0].url,
    ).toBeUndefined();
    expect(groupDeliverables([resource, unsafe]).details).toEqual([unsafe]);
  });
});

test('streamed additions and serialized history produce the same grouping', () => {
  const first = fixtureArtifact('first');
  const second = fixtureArtifact('second', { title: 'Final chart' });
  expect(groupDeliverables([first]).deliverables[0].artifact.id).toBe('first');
  const items = [first, second];
  expect(groupDeliverables(JSON.parse(JSON.stringify(items)))).toEqual(
    groupDeliverables(items),
  );
});

test('an explicitly unsaved preview with a source chart ID stays in work details', () => {
  const saved = fixtureArtifact('saved');
  const preview = fixtureArtifact('preview', {
    payload: { slice_id: 12, form_data_key: 'edit', saved: false },
  });
  expect(groupDeliverables([preview]).deliverables).toEqual([]);
  const grouped = groupDeliverables([saved, preview]);
  expect(grouped.deliverables[0].artifact).toBe(saved);
  expect(grouped.details).toEqual([preview]);
});

test('UUID-only charts require a real URL rather than an invented integer-ID route', () => {
  const chart = fixtureArtifact('uuid', {
    payload: { uuid: '3d9927dc-006e-4220-a889-25fcbf3966e1' },
  });
  expect(groupDeliverables([chart]).deliverables[0].url).toBeUndefined();
});
