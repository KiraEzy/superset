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

import { reduceTurn, Turn, TurnEvent } from './runtime';

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
