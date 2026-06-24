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
import { SupersetClient, getClientErrorObject } from '@superset-ui/core';
import { makeUrl } from 'src/utils/pathUtils';
import { AiConnectionConfig, getAiConnectionConfig } from './aiConnectionConfig';

type ProxyResponse = { ok: boolean; message: string; models?: string[] };

function extractErrorMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') {
    return null;
  }
  const record = payload as Record<string, unknown>;
  const nestedError = record.error;
  if (nestedError && typeof nestedError === 'object') {
    const nestedMessage = (nestedError as Record<string, unknown>).message;
    if (typeof nestedMessage === 'string' && nestedMessage.trim()) {
      return nestedMessage.trim();
    }
  }
  if (typeof record.message === 'string' && record.message.trim()) {
    return record.message.trim();
  }
  return null;
}

/** Turn API/LLM errors into readable chat text. */
export function formatAiChatError(error: unknown): string {
  const raw =
    error instanceof Error ? error.message : String(error ?? 'Request failed');

  const trimmed = raw.trim();
  if (!trimmed) {
    return 'Request failed';
  }

  try {
    const parsed = JSON.parse(trimmed) as unknown;
    const message = extractErrorMessage(parsed);
    if (message) {
      return message;
    }
  } catch {
    // not pure JSON — try embedded JSON blob (common for provider errors)
  }

  const jsonStart = trimmed.indexOf('{');
  if (jsonStart >= 0) {
    try {
      const parsed = JSON.parse(trimmed.slice(jsonStart)) as unknown;
      const message = extractErrorMessage(parsed);
      if (message) {
        return message;
      }
    } catch {
      // fall through to raw text
    }
  }

  return trimmed;
}

async function postAi<T>(endpoint: string, body: Record<string, unknown>): Promise<T> {
  try {
    const { json } = await SupersetClient.post({
      endpoint: `/api/v1/ai/${endpoint}`,
      jsonPayload: body,
    });
    return json as T;
  } catch (error) {
    const clientError = await getClientErrorObject(error);
    throw new Error(
      formatAiChatError(
        clientError.message || clientError.error || error || 'Request failed',
      ),
    );
  }
}

export async function testMcpConnection(
  config: Pick<AiConnectionConfig, 'mcpServerUrl' | 'mcpBearerToken'>,
): Promise<{ ok: boolean; message: string }> {
  return postAi<ProxyResponse>('test_mcp/', {
    mcpServerUrl: config.mcpServerUrl,
    mcpBearerToken: config.mcpBearerToken,
  });
}

export async function testLlmConnection(
  config: Pick<
    AiConnectionConfig,
    'llmApiBaseUrl' | 'llmApiKey' | 'llmModel'
  >,
): Promise<{ ok: boolean; message: string }> {
  return postAi<ProxyResponse>('test_llm/', {
    llmApiBaseUrl: config.llmApiBaseUrl,
    llmApiKey: config.llmApiKey,
    llmModel: config.llmModel,
  });
}

export interface ChatResponse {
  content: string;
  tools_used?: string[];
}

export type ChatStreamEvent =
  | { type: 'status'; message: string }
  | { type: 'tool_start'; tool: string }
  | { type: 'tool_end'; tool: string }
  | { type: 'token'; content: string }
  | { type: 'done'; content: string; tools_used?: string[] }
  | {
      type: 'error';
      message: string;
      source?: 'llm' | 'mcp' | 'agent';
      code?: string;
    };

export interface ChatStreamHandlers {
  onStatus?: (message: string) => void;
  onToolStart?: (tool: string) => void;
  onToolEnd?: (tool: string) => void;
  onToken?: (content: string) => void;
  onDone?: (response: ChatResponse) => void;
  onError?: (message: string) => void;
}

function parseSseDataLine(line: string): ChatStreamEvent | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith('data: ')) {
    return null;
  }
  try {
    return JSON.parse(trimmed.slice(6)) as ChatStreamEvent;
  } catch {
    return null;
  }
}

/** Split buffered SSE text into complete events and a trailing remainder. */
export function splitSseBuffer(buffer: string): {
  events: ChatStreamEvent[];
  remainder: string;
} {
  const parts = buffer.split('\n\n');
  const remainder = parts.pop() || '';
  const events: ChatStreamEvent[] = [];
  for (const part of parts) {
    const event = parseSseDataLine(part);
    if (event) {
      events.push(event);
    }
  }
  return { events, remainder };
}

/** Parse any final SSE event left in the buffer when the stream closes. */
export function flushSseBuffer(buffer: string): ChatStreamEvent[] {
  const trimmed = buffer.trim();
  if (!trimmed) {
    return [];
  }
  const event = parseSseDataLine(trimmed);
  return event ? [event] : [];
}

export function streamErrorMessage(event: Extract<ChatStreamEvent, { type: 'error' }>): string {
  if (event.message?.trim()) {
    return event.message.trim();
  }
  if (event.code?.trim()) {
    return event.code.trim();
  }
  return 'Request failed';
}

async function parseSseStream(
  response: Response,
  onEvent: (event: ChatStreamEvent) => void,
): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: !done });
    }

    const { events, remainder } = splitSseBuffer(buffer);
    buffer = remainder;
    for (const event of events) {
      onEvent(event);
    }

    if (done) {
      break;
    }
  }

  buffer += decoder.decode();
  for (const event of flushSseBuffer(buffer)) {
    onEvent(event);
  }
}

export async function streamChatMessage(
  messages: Array<{ role: 'user' | 'assistant'; content: string }>,
  config: AiConnectionConfig = getAiConnectionConfig(),
  handlers: ChatStreamHandlers = {},
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const csrfToken = await SupersetClient.getCSRFToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  };
  if (csrfToken) {
    headers['X-CSRFToken'] = csrfToken;
  }

  const response = await fetch(makeUrl('/api/v1/ai/chat/stream/'), {
    method: 'POST',
    headers,
    credentials: 'same-origin',
    body: JSON.stringify({
      ...config,
      messages,
    }),
    signal,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(formatAiChatError(text));
  }

  let content = '';
  const toolsUsed: string[] = [];
  let finished = false;
  let streamError: string | null = null;

  await parseSseStream(response, event => {
    switch (event.type) {
      case 'status':
        handlers.onStatus?.(event.message);
        break;
      case 'tool_start':
        handlers.onToolStart?.(event.tool);
        handlers.onStatus?.(`Calling ${event.tool}...`);
        break;
      case 'tool_end':
        handlers.onToolEnd?.(event.tool);
        break;
      case 'token':
        content += event.content;
        handlers.onToken?.(event.content);
        break;
      case 'done':
        content = event.content || content;
        if (event.tools_used?.length) {
          toolsUsed.push(...event.tools_used);
        }
        finished = true;
        handlers.onDone?.({ content, tools_used: toolsUsed });
        break;
      case 'error': {
        const message = streamErrorMessage(event);
        streamError = message;
        handlers.onError?.(message);
        break;
      }
      default:
        break;
    }
  });

  if (streamError) {
    throw new Error(formatAiChatError(streamError));
  }

  if (!finished && !content.trim()) {
    throw new Error('Chat ended without a response');
  }

  return { content: content.trim(), tools_used: toolsUsed };
}

export async function sendChatMessage(
  messages: Array<{ role: 'user' | 'assistant'; content: string }>,
  config: AiConnectionConfig = getAiConnectionConfig(),
): Promise<ChatResponse> {
  return postAi<ChatResponse>('chat/', {
    ...config,
    messages,
  });
}
