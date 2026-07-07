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

export const AI_CONNECTION_SETTINGS_PATH = '/ai/connection/';

const AI_CONNECTION_ENDPOINT = '/api/v1/ai_connection/';

export type LlmProvider =
  | 'lmstudio'
  | 'openai'
  | 'gemini'
  | 'deepseek'
  | 'custom';

export interface ProviderLlmSettings {
  llmApiBaseUrl: string;
  llmModel: string;
  llmApiKey: string;
}

export interface AiConnectionConfig extends ProviderLlmSettings {
  llmProvider: LlmProvider;
  mcpEnabled: boolean;
  mcpServerUrl: string;
  mcpBearerToken: string;
  agentMaxIterations: number;
  systemPrompt: string;
}

export interface StoredAiConnectionState {
  llmProvider: LlmProvider;
  providerSettings: Partial<Record<LlmProvider, ProviderLlmSettings>>;
  mcpEnabled: boolean;
  mcpServerUrl: string;
  mcpBearerToken: string;
  agentMaxIterations: number;
  systemPrompt: string;
}

export const LLM_PROVIDER_PRESETS: Record<
  LlmProvider,
  { llmApiBaseUrl: string; llmModel: string }
> = {
  lmstudio: {
    llmApiBaseUrl: 'http://localhost:1234/v1',
    llmModel: '',
  },
  openai: {
    llmApiBaseUrl: 'https://api.openai.com/v1',
    llmModel: 'gpt-4o-mini',
  },
  gemini: {
    llmApiBaseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    llmModel: 'gemini-2.5-flash',
  },
  deepseek: {
    llmApiBaseUrl: 'https://api.deepseek.com/v1',
    llmModel: 'deepseek-chat',
  },
  custom: {
    llmApiBaseUrl: '',
    llmModel: '',
  },
};

const DEFAULT_MCP = {
  mcpEnabled: true,
  mcpServerUrl: 'http://localhost:5008/mcp',
  mcpBearerToken: '',
};

const DEFAULT_AGENT = {
  agentMaxIterations: 120,
  systemPrompt: '',
};

export const AGENT_MAX_ITERATIONS_MIN = 1;
export const AGENT_MAX_ITERATIONS_MAX = 500;

export const DEFAULT_AI_CONNECTION_CONFIG: AiConnectionConfig = {
  llmProvider: 'gemini',
  ...LLM_PROVIDER_PRESETS.gemini,
  llmApiKey: '',
  ...DEFAULT_MCP,
  ...DEFAULT_AGENT,
};

export function getDefaultProviderLlmSettings(
  provider: LlmProvider,
): ProviderLlmSettings {
  const preset = LLM_PROVIDER_PRESETS[provider];
  return {
    llmApiBaseUrl: preset.llmApiBaseUrl,
    llmModel: preset.llmModel,
    llmApiKey: '',
  };
}

export function isLlmProvider(value: unknown): value is LlmProvider {
  return (
    value === 'lmstudio' ||
    value === 'openai' ||
    value === 'gemini' ||
    value === 'deepseek' ||
    value === 'custom'
  );
}

export function extractLlmSettings(
  source: Partial<AiConnectionConfig>,
): ProviderLlmSettings {
  return {
    llmApiBaseUrl: source.llmApiBaseUrl ?? '',
    llmModel: source.llmModel ?? '',
    llmApiKey: source.llmApiKey ?? '',
  };
}

function parseAgentMaxIterations(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    const rounded = Math.round(value);
    if (
      rounded >= AGENT_MAX_ITERATIONS_MIN &&
      rounded <= AGENT_MAX_ITERATIONS_MAX
    ) {
      return rounded;
    }
  }
  return DEFAULT_AGENT.agentMaxIterations;
}

function parseSystemPrompt(value: unknown): string {
  return typeof value === 'string' ? value : DEFAULT_AGENT.systemPrompt;
}

function defaultStoredState(): StoredAiConnectionState {
  return {
    llmProvider: DEFAULT_AI_CONNECTION_CONFIG.llmProvider,
    providerSettings: {},
    ...DEFAULT_MCP,
    ...DEFAULT_AGENT,
  };
}

function normalizeStoredState(
  parsed: Record<string, unknown>,
): StoredAiConnectionState {
  const provider = isLlmProvider(parsed.llmProvider)
    ? parsed.llmProvider
    : DEFAULT_AI_CONNECTION_CONFIG.llmProvider;
  const providerSettings =
    parsed.providerSettings && typeof parsed.providerSettings === 'object'
      ? (parsed.providerSettings as StoredAiConnectionState['providerSettings'])
      : {};
  return {
    llmProvider: provider,
    providerSettings,
    mcpEnabled:
      typeof parsed.mcpEnabled === 'boolean'
        ? parsed.mcpEnabled
        : DEFAULT_MCP.mcpEnabled,
    mcpServerUrl:
      typeof parsed.mcpServerUrl === 'string'
        ? parsed.mcpServerUrl
        : DEFAULT_MCP.mcpServerUrl,
    mcpBearerToken:
      typeof parsed.mcpBearerToken === 'string'
        ? parsed.mcpBearerToken
        : DEFAULT_MCP.mcpBearerToken,
    agentMaxIterations: parseAgentMaxIterations(parsed.agentMaxIterations),
    systemPrompt: parseSystemPrompt(parsed.systemPrompt),
  };
}

export function buildConfigFromState(
  state: StoredAiConnectionState,
): AiConnectionConfig {
  const provider = state.llmProvider;
  const llm =
    state.providerSettings[provider] ?? getDefaultProviderLlmSettings(provider);
  return {
    llmProvider: provider,
    ...llm,
    mcpEnabled: state.mcpEnabled,
    mcpServerUrl: state.mcpServerUrl,
    mcpBearerToken: state.mcpBearerToken,
    agentMaxIterations: state.agentMaxIterations,
    systemPrompt: state.systemPrompt,
  };
}

/** Fold the active provider's flat form config back into the stored state. */
export function mergeConfigIntoState(
  state: StoredAiConnectionState,
  config: AiConnectionConfig,
): StoredAiConnectionState {
  return {
    ...state,
    llmProvider: config.llmProvider,
    providerSettings: {
      ...state.providerSettings,
      [config.llmProvider]: extractLlmSettings(config),
    },
    mcpEnabled: config.mcpEnabled,
    mcpServerUrl: config.mcpServerUrl,
    mcpBearerToken: config.mcpBearerToken,
    agentMaxIterations: parseAgentMaxIterations(config.agentMaxIterations),
    systemPrompt: parseSystemPrompt(config.systemPrompt),
  };
}

/** Load the global AI connection config from the backend. */
export async function fetchAiConnectionState(): Promise<StoredAiConnectionState> {
  try {
    const { json } = await SupersetClient.get({
      endpoint: AI_CONNECTION_ENDPOINT,
    });
    const result = (json as { result?: Record<string, unknown> })?.result;
    if (result && typeof result === 'object') {
      return normalizeStoredState(result);
    }
    return defaultStoredState();
  } catch (error) {
    const clientError = await getClientErrorObject(error);
    throw new Error(
      clientError.message || clientError.error || 'Failed to load AI config',
    );
  }
}

/** Persist the global AI connection config to the backend. */
export async function saveAiConnectionState(
  state: StoredAiConnectionState,
): Promise<StoredAiConnectionState> {
  try {
    const { json } = await SupersetClient.put({
      endpoint: AI_CONNECTION_ENDPOINT,
      jsonPayload: state,
    });
    const result = (json as { result?: Record<string, unknown> })?.result;
    if (result && typeof result === 'object') {
      return normalizeStoredState(result);
    }
    return state;
  } catch (error) {
    const clientError = await getClientErrorObject(error);
    throw new Error(
      clientError.message || clientError.error || 'Failed to save AI config',
    );
  }
}
