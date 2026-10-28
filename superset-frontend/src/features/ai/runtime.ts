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

export type ApprovalMode = 'ask' | 'full_access';

export interface RuntimeMetadata {
  enabled: boolean;
  models?: import('./modelCatalog').PublicModel[];
  image_limits?: { count: number; bytes: number; pixels: number };
  post?: { id: number; name: string };
  workflows: { id: string; name: string; description?: string }[];
}
export interface RuntimeContext {
  type: 'chart' | 'dashboard' | 'dataset';
  id: number;
  filters?: Record<string, unknown>;
}
export interface Artifact {
  id: string;
  type: string;
  title: string;
  payload: Record<string, unknown>;
  provenance?: Record<string, unknown>;
  version: number;
  saved: boolean;
}
export interface PendingRequest {
  id: string;
  kind: 'clarification' | 'approval' | 'review' | 'connection';
  message: string;
  options?: string[];
  scope?: string;
  expires_at?: string;
  tool?: string;
  arguments?: Record<string, unknown>;
  schema?: Record<string, unknown>;
}
export interface ContextUsage {
  model: string;
  model_id?: string | null;
  context_window_tokens: number;
  input_tokens: number;
  output_tokens: number;
  output_limit_tokens: number;
  input_allowance_tokens: number;
  tool_result_reserve_tokens: number;
  estimated: boolean;
}
export interface Turn {
  approval_mode?: ApprovalMode;
  context_usage?: ContextUsage | null;
  activity?: WorkActivityData;
  id: string;
  thread_id: string;
  status: string;
  content: string;
  items: {
    id: string;
    kind: string;
    status: string;
    payload: Record<string, unknown>;
  }[];
  artifacts: Artifact[];
  pending_requests: PendingRequest[];
  last_sequence: number;
  error?: string | { message: string; code?: string };
}
export interface WorkActivityData {
  duration_seconds: number | null;
  status: string;
  items: Turn['items'];
}
export interface TurnEvent {
  schema_version: 1;
  thread_id: string;
  turn_id: string;
  sequence: number;
  type: string;
  payload: Record<string, unknown>;
}
export const isTerminal = (turn: Turn) =>
  ['completed', 'failed', 'cancelled', 'canceled'].includes(turn.status);

/** Ignore duplicate, stale and cross-turn events; terminal snapshots own final state. */
export function reduceTurn(state: Turn | null, event: TurnEvent): Turn | null {
  if (
    !state ||
    state.id !== event.turn_id ||
    state.thread_id !== event.thread_id ||
    event.schema_version !== 1 ||
    event.sequence <= state.last_sequence ||
    isTerminal(state)
  )
    return state;
  if (event.type === 'turn_completed' || event.type === 'turn_failed') {
    return {
      ...(event.payload.turn as unknown as Turn),
      last_sequence: event.sequence,
    };
  }
  const next = { ...state, last_sequence: event.sequence };
  if (event.type === 'usage')
    next.context_usage = event.payload.usage as ContextUsage;
  if (event.type === 'message_delta')
    next.content += String(event.payload.content ?? '');
  if (event.type === 'message_reset')
    next.content = String(event.payload.content ?? '');
  if (event.type === 'status' && typeof event.payload.status === 'string')
    next.status = event.payload.status;
  if (
    event.payload.approval_mode === 'ask' ||
    event.payload.approval_mode === 'full_access'
  )
    next.approval_mode = event.payload.approval_mode;
  if (event.type === 'activity_updated') {
    const item = event.payload.item as Turn['items'][number] | undefined;
    if (
      item &&
      typeof item.id === 'string' &&
      typeof item.kind === 'string' &&
      typeof item.status === 'string' &&
      item.payload &&
      typeof item.payload === 'object'
    ) {
      const upsert = (items: Turn['items']) =>
        items.some(value => value.id === item.id)
          ? items.map(value => (value.id === item.id ? item : value))
          : [...items, item];
      next.items = upsert(state.items);
      next.activity = {
        duration_seconds: state.activity?.duration_seconds ?? null,
        status: next.status,
        items: upsert(state.activity?.items ?? []),
      };
    }
  }
  if (next.activity && next.activity.status !== next.status)
    next.activity = { ...next.activity, status: next.status };
  if (event.type === 'artifact') {
    const artifact = event.payload.artifact as unknown as Artifact;
    next.artifacts = [
      ...state.artifacts.filter(item => item.id !== artifact.id),
      artifact,
    ];
  }
  if (event.type === 'request') {
    const request = event.payload.request as unknown as PendingRequest;
    next.pending_requests = [
      ...state.pending_requests.filter(item => item.id !== request.id),
      request,
    ];
  }
  return next;
}
export async function runtimeGet<T>(path: string): Promise<T> {
  const { json } = await SupersetClient.get({ endpoint: `/api/v1/ai/${path}` });
  return (json.result ?? json) as T;
}
export async function runtimePost<T>(path: string, body: object): Promise<T> {
  try {
    const { json } = await SupersetClient.post({
      endpoint: `/api/v1/ai/${path}`,
      jsonPayload: body,
    });
    return (json.result ?? json) as T;
  } catch (error) {
    const parsed = await getClientErrorObject(
      error as Parameters<typeof getClientErrorObject>[0],
    );
    throw new Error(
      parsed.message || parsed.error || 'Request failed. Try again.',
    );
  }
}

export interface ImageReference {
  id: string;
  name: string;
  url: string;
}
