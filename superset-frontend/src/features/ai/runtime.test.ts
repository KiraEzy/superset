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

import { reduceTurn, runtimePost, Turn, TurnEvent } from './runtime';
import { SupersetClient } from '@superset-ui/core';

const turn: Turn = {
  id: 'turn',
  thread_id: 'thread',
  status: 'running',
  content: '',
  items: [],
  artifacts: [],
  pending_requests: [],
  last_sequence: 0,
};
const event: TurnEvent = {
  schema_version: 1,
  thread_id: 'thread',
  turn_id: 'turn',
  sequence: 1,
  type: 'message_delta',
  payload: { content: 'Hello' },
};
test('replayed events never duplicate assistant text', () => {
  const next = reduceTurn(turn, event);
  expect(next?.content).toBe('Hello');
  expect(reduceTurn(next, event)).toBe(next);
});
test('cross-thread and cross-turn events cannot contaminate conversation', () => {
  expect(reduceTurn(turn, { ...event, thread_id: 'other' })).toBe(turn);
  expect(reduceTurn(turn, { ...event, turn_id: 'other' })).toBe(turn);
});
test('terminal snapshot replaces partial content and rejects late deltas', () => {
  const snapshot = { ...turn, status: 'completed', content: 'Final answer' };
  const next = reduceTurn(turn, {
    ...event,
    type: 'turn_completed',
    payload: { turn: snapshot },
  });
  expect(next?.content).toBe('Final answer');
  expect(reduceTurn(next, { ...event, sequence: 2 })).toBe(next);
});

test('activity snapshots upsert in place and reject stale replay', () => {
  const update: TurnEvent = {
    ...event,
    type: 'activity_updated',
    payload: {
      item: {
        id: 'summary',
        kind: 'reasoning_summary',
        status: 'running',
        payload: { message: 'Checking' },
      },
    },
  };
  const first = reduceTurn(turn, update)!;
  const second = reduceTurn(first, {
    ...update,
    sequence: 2,
    payload: {
      item: { ...first.items[0], payload: { message: 'Checking datasets' } },
    },
  })!;
  expect(second.items).toHaveLength(1);
  expect(second.activity?.items[0].payload.message).toBe('Checking datasets');
  expect(reduceTurn(second, update)).toBe(second);
  const completed = reduceTurn(second, {
    ...update,
    sequence: 3,
    type: 'status',
    payload: { status: 'waiting_approval' },
  });
  expect(completed?.activity?.status).toBe('waiting_approval');
});

test('recovery reset replaces partial text and replay does not append it twice', () => {
  const partial = reduceTurn(turn, event);
  const reset = {
    ...event,
    sequence: 2,
    type: 'message_reset',
    payload: { content: 'Recovered' },
  };
  const recovered = reduceTurn(partial, reset);
  expect(recovered?.content).toBe('Recovered');
  expect(reduceTurn(recovered, reset)).toBe(recovered);
  expect(reduceTurn(recovered, event)).toBe(recovered);
  expect(
    reduceTurn(recovered, {
      ...event,
      sequence: 3,
      payload: { content: ' final' },
    })?.content,
  ).toBe('Recovered final');
});

test('runtime posts expose server validation messages instead of a generic failure', async () => {
  const post = jest.spyOn(SupersetClient, 'post').mockRejectedValueOnce({
    response: new Response(
      JSON.stringify({ message: 'Request expired', code: 'request_expired' }),
      {
        status: 409,
        headers: { 'Content-Type': 'application/json' },
      },
    ),
  });
  try {
    await expect(runtimePost('turns/test/input', {})).rejects.toThrow(
      'Request expired',
    );
  } finally {
    post.mockRestore();
  }
});

test('deliverable events replace versions by stable key and reject replay', () => {
  const entry = {
    key: 'chart',
    artifact_id: 'one',
    title: 'Chart',
    type: 'chart',
    saved: true,
    version: 1,
    available: true,
  };
  const update = {
    ...event,
    type: 'deliverable',
    payload: { deliverable: entry },
  };
  const first = reduceTurn(turn, update);
  expect(first?.deliverables).toEqual([entry]);
  expect(reduceTurn(first, update)).toBe(first);
  const next = reduceTurn(first, {
    ...update,
    sequence: 2,
    payload: { deliverable: { ...entry, artifact_id: 'two', version: 2 } },
  });
  expect(next?.deliverables).toHaveLength(1);
  expect(next?.deliverables?.[0].artifact_id).toBe('two');
});

test('a confirmed dashboard rebuild replaces the registry without replaying retired entries', () => {
  const state = {
    ...turn,
    deliverables: [
      {
        key: 'old',
        artifact_id: 'old',
        title: 'Draft',
        type: 'chart' as const,
        saved: true,
        version: 1,
        available: true,
      },
    ],
  };
  const update = {
    ...event,
    type: 'deliverable',
    payload: { deliverables: [] },
  };
  const next = reduceTurn(state, update);
  expect(next?.deliverables).toEqual([]);
  expect(reduceTurn(next, update)).toBe(next);
});
