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
import { SupersetClient } from '@superset-ui/core';
import {
  generateSessionTitle,
  listChatSessions,
  mapApiMessage,
  mapApiSession,
  mapApiSessionSummary,
} from './aiChatSessionApi';

jest.mock('@superset-ui/core', () => ({
  SupersetClient: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
  },
  getClientErrorObject: jest.fn(async error => ({ message: String(error) })),
}));

const mockedGet = SupersetClient.get as jest.Mock;

describe('aiChatSessionApi', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('mapApiSessionSummary maps uuid to id', () => {
    const summary = mapApiSessionSummary({
      id: 1,
      uuid: '11111111-1111-1111-1111-111111111111',
      title: 'Test',
      created_on: '2026-01-01T00:00:00',
      changed_on: '2026-01-02T00:00:00',
    });

    expect(summary.id).toBe('11111111-1111-1111-1111-111111111111');
    expect(summary.dbId).toBe(1);
    expect(summary.title).toBe('Test');
  });

  test('mapApiSession maps nested messages', () => {
    const session = mapApiSession({
      id: 2,
      uuid: '22222222-2222-2222-2222-222222222222',
      title: 'Chat',
      created_on: '2026-01-01T00:00:00',
      changed_on: '2026-01-02T00:00:00',
      messages: [
        {
          id: 10,
          role: 'user',
          content: 'Hello',
          created_on: '2026-01-01T00:01:00',
        },
      ],
    });

    expect(session.messages).toHaveLength(1);
    expect(session.messages[0].content).toBe('Hello');
    expect(session.messages[0].id).toBe('10');
  });

  test('generateSessionTitle truncates long text', () => {
    const title = generateSessionTitle(
      'This is a very long first message that should be truncated',
    );
    expect(title.endsWith('...')).toBe(true);
    expect(title.length).toBeLessThanOrEqual(33);
  });

  test('listChatSessions requests ordered session list', async () => {
    mockedGet.mockResolvedValue({
      json: {
        result: [
          {
            id: 1,
            uuid: '33333333-3333-3333-3333-333333333333',
            title: 'One',
            created_on: '2026-01-01T00:00:00',
            changed_on: '2026-01-02T00:00:00',
          },
        ],
      },
    });

    const sessions = await listChatSessions();

    expect(mockedGet).toHaveBeenCalledWith({
      endpoint:
        '/api/v1/ai_chat_session/?q=(order_column:changed_on,order_direction:desc,page:0,page_size:100)',
    });
    expect(sessions).toHaveLength(1);
    expect(sessions[0].title).toBe('One');
  });

  test('mapApiMessage maps charts from extra', () => {
    const message = mapApiMessage({
      id: 5,
      role: 'assistant',
      content: 'Here is your chart',
      created_on: '2026-01-01T00:00:00',
      extra: {
        charts: [
          {
            id: 'chart-0',
            viz_type: 'pie',
            slice_id: 42,
            form_data: { viz_type: 'pie' },
          },
        ],
      },
    });

    expect(message.charts).toHaveLength(1);
    expect(message.charts?.[0].slice_id).toBe(42);
  });

  test('mapApiMessage maps duration_seconds from extra', () => {
    const message = mapApiMessage({
      id: 6,
      role: 'assistant',
      content: 'Done',
      created_on: '2026-01-01T00:00:00',
      extra: { duration_seconds: 12 },
    });

    expect(message.durationSeconds).toBe(12);
  });
});
