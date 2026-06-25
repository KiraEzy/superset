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

export const AI_CONNECTION_SETTINGS_PATH = '/ai/connection/';

const STORAGE_KEY = 'focalbi__ai_connection_config';

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

interface StoredAiConnectionState {
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

function isLlmProvider(value: unknown): value is LlmProvider {
  return (
    value === 'lmstudio' ||
    value === 'openai' ||
    value === 'gemini' ||
    value === 'deepseek' ||
    value === 'custom'
  );
}

function extractLlmSettings(
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

function buildConfigFromState(state: StoredAiConnectionState): AiConnectionConfig {
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

function migrateLegacyConfig(
  parsed: Record<string, unknown>,
): StoredAiConnectionState {
  const provider = isLlmProvider(parsed.llmProvider)
    ? parsed.llmProvider
    : DEFAULT_AI_CONNECTION_CONFIG.llmProvider;

  return {
    llmProvider: provider,
    providerSettings: {
      [provider]: extractLlmSettings(parsed as Partial<AiConnectionConfig>),
    },
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

function loadStoredState(): StoredAiConnectionState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return {
        llmProvider: DEFAULT_AI_CONNECTION_CONFIG.llmProvider,
        providerSettings: {},
        ...DEFAULT_MCP,
        ...DEFAULT_AGENT,
      };
    }

    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (parsed.providerSettings && typeof parsed.providerSettings === 'object') {
      const provider = isLlmProvider(parsed.llmProvider)
        ? parsed.llmProvider
        : DEFAULT_AI_CONNECTION_CONFIG.llmProvider;
      return {
        llmProvider: provider,
        providerSettings:
          parsed.providerSettings as StoredAiConnectionState['providerSettings'],
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

    return migrateLegacyConfig(parsed);
  } catch {
    return {
      llmProvider: DEFAULT_AI_CONNECTION_CONFIG.llmProvider,
      providerSettings: {},
      ...DEFAULT_MCP,
      ...DEFAULT_AGENT,
    };
  }
}

function writeStoredState(state: StoredAiConnectionState): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function getProviderLlmSettings(
  provider: LlmProvider,
): ProviderLlmSettings {
  const state = loadStoredState();
  return state.providerSettings[provider] ?? getDefaultProviderLlmSettings(provider);
}

export function getAiConnectionConfig(): AiConnectionConfig {
  return buildConfigFromState(loadStoredState());
}

export function saveAiConnectionConfig(config: AiConnectionConfig): void {
  const state = loadStoredState();
  state.llmProvider = config.llmProvider;
  state.providerSettings[config.llmProvider] = extractLlmSettings(config);
  state.mcpEnabled = config.mcpEnabled;
  state.mcpServerUrl = config.mcpServerUrl;
  state.mcpBearerToken = config.mcpBearerToken;
  state.agentMaxIterations = parseAgentMaxIterations(config.agentMaxIterations);
  state.systemPrompt = parseSystemPrompt(config.systemPrompt);
  writeStoredState(state);
}

export function stashProviderLlmSettings(
  provider: LlmProvider,
  settings: ProviderLlmSettings,
): void {
  const state = loadStoredState();
  state.providerSettings[provider] = settings;
  writeStoredState(state);
}

/** Remember the current provider's LLM fields, then load the target provider. */
export function switchAiConnectionProvider(
  fromProvider: LlmProvider,
  currentLlm: ProviderLlmSettings,
  toProvider: LlmProvider,
): AiConnectionConfig {
  const state = loadStoredState();
  state.providerSettings[fromProvider] = currentLlm;
  state.llmProvider = toProvider;
  writeStoredState(state);
  return buildConfigFromState(state);
}
