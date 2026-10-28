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

export interface AiChatChartPayload {
  id: string;
  title?: string;
  viz_type: string;
  slice_id?: number;
  explore_url?: string;
  form_data: Record<string, unknown>;
  form_data_key?: string;
}

export interface GenerationActivityEntry {
  type?: string;
  message: string;
  at: string;
}

export interface ChatMessage {
  attachments?: import('./runtime').ImageReference[];
  activity?: import('./runtime').WorkActivityData;
  runtimeTurnId?: string;
  artifacts?: import('./runtime').Artifact[];
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  error?: boolean;
  streaming?: boolean;
  status?: string;
  charts?: AiChatChartPayload[];
  /** Wall-clock seconds to complete the assistant response (stream end). */
  durationSeconds?: number;
}

export interface ChatSessionSummary {
  isPinned?: boolean;
  id: string;
  dbId: number;
  title: string;
  createdAt: number;
  updatedAt: number;
}

export interface ChatSession extends ChatSessionSummary {
  deliverables?: import('./runtime').PresentedDeliverable[];
  modelId?: string;
  activeTurn?: { id: string; status: string } | null;
  latestTurn?: { id: string; status: string } | null;
  messages: ChatMessage[];
}

export interface ApiChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  extra?: Record<string, unknown>;
  created_on: string;
}

export interface ApiChatSessionSummary {
  is_pinned?: boolean;
  id: number;
  uuid: string;
  title: string;
  created_on: string;
  changed_on: string;
}

export interface ApiChatSession extends ApiChatSessionSummary {
  deliverables?: import('./runtime').PresentedDeliverable[];
  model_id?: string;
  active_turn?: { id: string; status: string } | null;
  latest_turn?: { id: string; status: string } | null;
  messages?: ApiChatMessage[];
}
