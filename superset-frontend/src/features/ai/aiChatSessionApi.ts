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
import { formatAiChatError } from './aiChatApi';
import {
  ApiChatMessage,
  ApiChatSession,
  ApiChatSessionSummary,
  ChatMessage,
  ChatSession,
  ChatSessionSummary,
} from './types';

function toTimestamp(value: string | undefined): number {
  if (!value) {
    return Date.now();
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? Date.now() : parsed;
}

export function mapApiMessage(message: ApiChatMessage): ChatMessage {
  const extra = message.extra ?? {};
  return {
    id: String(message.id),
    role: message.role,
    content: message.content,
    timestamp: toTimestamp(message.created_on),
    error: Boolean(extra.error),
  };
}

export function mapApiSessionSummary(
  session: ApiChatSessionSummary,
): ChatSessionSummary {
  return {
    id: session.uuid,
    dbId: session.id,
    title: session.title,
    createdAt: toTimestamp(session.created_on),
    updatedAt: toTimestamp(session.changed_on),
  };
}

export function mapApiSession(session: ApiChatSession): ChatSession {
  return {
    ...mapApiSessionSummary(session),
    messages: (session.messages ?? []).map(mapApiMessage),
  };
}

type ClientErrorInput = Parameters<typeof getClientErrorObject>[0];

function risonEncode(value: Record<string, unknown>): string {
  const entries = Object.entries(value).map(([key, val]) => {
    if (typeof val === 'string') {
      return `${key}:${val}`;
    }
    if (typeof val === 'number') {
      return `${key}:${val}`;
    }
    return `${key}:${String(val)}`;
  });
  return `(${entries.join(',')})`;
}

async function throwFormattedClientError(error: unknown): Promise<never> {
  const clientError = await getClientErrorObject(error as ClientErrorInput);
  throw new Error(
    formatAiChatError(
      clientError.message || clientError.error || error || 'Request failed',
    ),
  );
}

export async function listChatSessions(): Promise<ChatSessionSummary[]> {
  const query = risonEncode({
    order_column: 'changed_on',
    order_direction: 'desc',
    page: 0,
    page_size: 100,
  });
  try {
    const { json } = await SupersetClient.get({
      endpoint: `/api/v1/ai_chat_session/?q=${query}`,
    });
    const result = (json?.result ?? []) as ApiChatSessionSummary[];
    return result.map(mapApiSessionSummary);
  } catch (error) {
    return throwFormattedClientError(error);
  }
}

export async function getChatSessionByUuid(
  sessionUuid: string,
): Promise<ChatSession> {
  try {
    const { json } = await SupersetClient.get({
      endpoint: `/api/v1/ai_chat_session/${sessionUuid}`,
    });
    return mapApiSession(json.result as ApiChatSession);
  } catch (error) {
    return throwFormattedClientError(error);
  }
}

export async function createChatSession(
  title = 'New chat',
): Promise<ChatSession> {
  try {
    const { json } = await SupersetClient.post({
      endpoint: '/api/v1/ai_chat_session/',
      jsonPayload: { title },
    });
    return mapApiSession(json.result as ApiChatSession);
  } catch (error) {
    return throwFormattedClientError(error);
  }
}

export async function updateChatSessionTitle(
  sessionUuid: string,
  title: string,
): Promise<ChatSessionSummary> {
  try {
    const { json } = await SupersetClient.put({
      endpoint: `/api/v1/ai_chat_session/${sessionUuid}`,
      jsonPayload: { title },
    });
    return mapApiSessionSummary(json.result as ApiChatSessionSummary);
  } catch (error) {
    return throwFormattedClientError(error);
  }
}

export async function deleteChatSession(sessionUuid: string): Promise<void> {
  try {
    await SupersetClient.delete({
      endpoint: `/api/v1/ai_chat_session/${sessionUuid}`,
    });
  } catch (error) {
    await throwFormattedClientError(error);
  }
}

export interface AppendMessagePayload {
  role: 'user' | 'assistant';
  content: string;
  extra?: Record<string, unknown>;
}

export async function appendChatMessage(
  sessionUuid: string,
  message: AppendMessagePayload,
): Promise<{ message: ChatMessage; session: ChatSessionSummary | null }> {
  try {
    const { json } = await SupersetClient.post({
      endpoint: `/api/v1/ai_chat_session/${sessionUuid}/message/`,
      jsonPayload: message,
    });
    const result = json.result as {
      message: ApiChatMessage;
      session: ApiChatSessionSummary | null;
    };
    return {
      message: mapApiMessage(result.message),
      session: result.session ? mapApiSessionSummary(result.session) : null,
    };
  } catch (error) {
    return throwFormattedClientError(error);
  }
}

export function generateSessionTitle(firstMessage: string): string {
  const maxLen = 30;
  const trimmed = firstMessage.trim().replace(/\n/g, ' ');
  return trimmed.length > maxLen ? `${trimmed.slice(0, maxLen)}...` : trimmed;
}
