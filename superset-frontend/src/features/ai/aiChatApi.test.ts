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
  flushSseBuffer,
  splitSseBuffer,
  streamChatMessage,
  streamErrorMessage,
} from './aiChatApi';

function createSseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  let index = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(encoder.encode(chunks[index]));
        index += 1;
        if (index === chunks.length) {
          controller.close();
        }
      }
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

// eslint-disable-next-line no-restricted-globals -- TODO: Migrate from describe blocks
describe('aiChatApi SSE parsing', () => {
  test('flushSseBuffer parses a trailing error event without a final delimiter', () => {
    const events = flushSseBuffer(
      'data: {"type": "error", "message": "Insufficient Balance"}',
    );
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({
      type: 'error',
      message: 'Insufficient Balance',
    });
  });

  test('splitSseBuffer handles an error event split across chunks', () => {
    const first = splitSseBuffer('data: {"type": "error", "message": "Insuff');
    expect(first.events).toHaveLength(0);
    expect(first.remainder).toBe('data: {"type": "error", "message": "Insuff');

    const second = splitSseBuffer(
      `${first.remainder}icient Balance"}\n\n`,
    );
    expect(second.events).toHaveLength(1);
    expect(second.events[0]).toEqual({
      type: 'error',
      message: 'Insufficient Balance',
    });
  });

  test('streamErrorMessage prefers message and falls back to code', () => {
    expect(
      streamErrorMessage({
        type: 'error',
        message: 'Insufficient Balance',
        source: 'llm',
      }),
    ).toBe('Insufficient Balance');
    expect(
      streamErrorMessage({
        type: 'error',
        message: '',
        code: 'insufficient_balance',
      }),
    ).toBe('insufficient_balance');
  });
});

// eslint-disable-next-line no-restricted-globals -- TODO: Migrate from describe blocks
describe('streamChatMessage', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    jest.spyOn(SupersetClient, 'getCSRFToken').mockResolvedValue('csrf-token');
  });

  afterEach(() => {
    global.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  test('surfaces provider error from the final SSE chunk', async () => {
    global.fetch = jest.fn().mockResolvedValue(
      createSseResponse([
        'data: {"type": "status", "message": "Thinking..."}\n\n',
        'data: {"type": "error", "message": "Insufficient Balance", "source": "llm"}',
      ]),
    );

    await expect(
      streamChatMessage([{ role: 'user', content: 'hello' }]),
    ).rejects.toThrow('Insufficient Balance');
  });

  test('does not mask provider errors with the generic fallback', async () => {
    global.fetch = jest.fn().mockResolvedValue(
      createSseResponse([
        'data: {"type": "error", "message": "Insufficient Balance"}\n\n',
      ]),
    );

    await expect(
      streamChatMessage([{ role: 'user', content: 'hello' }]),
    ).rejects.toThrow('Insufficient Balance');
  });

  test('aborts in-flight stream when signal is aborted', async () => {
    const controller = new AbortController();
    controller.abort();

    global.fetch = jest.fn().mockRejectedValue(
      new DOMException('Aborted', 'AbortError'),
    );

    await expect(
      streamChatMessage(
        [{ role: 'user', content: 'hello' }],
        {},
        controller.signal,
      ),
    ).rejects.toMatchObject({ name: 'AbortError' });
  });

  test('parses chart SSE events and includes charts in response', async () => {
    const chartPayload = {
      id: 'chart-0',
      viz_type: 'pie',
      form_data: { viz_type: 'pie', datasource: '1__table' },
      slice_id: 42,
      title: 'Revenue',
    };
    global.fetch = jest.fn().mockResolvedValue(
      createSseResponse([
        `data: ${JSON.stringify({ type: 'chart', chart: chartPayload })}\n\n`,
        `data: ${JSON.stringify({
          type: 'done',
          content: 'Here is your chart.',
          tools_used: ['generate_chart'],
          charts: [chartPayload],
        })}\n\n`,
      ]),
    );

    const onChart = jest.fn();
    const result = await streamChatMessage(
      [{ role: 'user', content: 'chart please' }],
      { onChart },
    );

    expect(onChart).toHaveBeenCalledWith(chartPayload);
    expect(result.charts).toEqual([chartPayload]);
    expect(result.content).toBe('Here is your chart.');
  });
});
