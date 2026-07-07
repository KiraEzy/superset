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

import { existsSync, readFileSync } from 'fs';
import { join } from 'path';
import type { Page } from '@playwright/test';

/** Global AI connection config REST endpoint. */
export const AI_CONNECTION_ENDPOINT = '/api/v1/ai_connection/';

const DEFAULT_CONFIG_PATH = join(
  process.cwd(),
  'config',
  'ai-connection.test.local.json',
);

type LlmProvider =
  | 'lmstudio'
  | 'openai'
  | 'gemini'
  | 'deepseek'
  | 'custom';

export interface AiConnectionTestConfig {
  llmProvider: LlmProvider;
  llmApiBaseUrl: string;
  llmModel: string;
  llmApiKey: string;
  mcpEnabled: boolean;
  mcpServerUrl: string;
  mcpBearerToken: string;
  agentMaxIterations: number;
  systemPrompt: string;
}

interface StoredAiConnectionState {
  llmProvider: LlmProvider;
  providerSettings: Partial<
    Record<
      LlmProvider,
      { llmApiBaseUrl: string; llmModel: string; llmApiKey: string }
    >
  >;
  mcpEnabled: boolean;
  mcpServerUrl: string;
  mcpBearerToken: string;
  agentMaxIterations: number;
  systemPrompt: string;
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

function parseConfig(raw: unknown): AiConnectionTestConfig | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const data = raw as Record<string, unknown>;
  if (!isLlmProvider(data.llmProvider)) {
    return null;
  }
  if (
    typeof data.llmApiBaseUrl !== 'string' ||
    typeof data.llmModel !== 'string' ||
    typeof data.llmApiKey !== 'string'
  ) {
    return null;
  }
  return {
    llmProvider: data.llmProvider,
    llmApiBaseUrl: data.llmApiBaseUrl,
    llmModel: data.llmModel,
    llmApiKey: data.llmApiKey,
    mcpEnabled: data.mcpEnabled !== false,
    mcpServerUrl:
      typeof data.mcpServerUrl === 'string' ? data.mcpServerUrl : '',
    mcpBearerToken:
      typeof data.mcpBearerToken === 'string' ? data.mcpBearerToken : '',
    agentMaxIterations:
      typeof data.agentMaxIterations === 'number' &&
      Number.isFinite(data.agentMaxIterations)
        ? Math.round(data.agentMaxIterations)
        : 120,
    systemPrompt:
      typeof data.systemPrompt === 'string' ? data.systemPrompt : '',
  };
}

export function getAiConnectionTestConfigPath(): string {
  return process.env.FOCALBI_AI_CONNECTION_TEST_CONFIG || DEFAULT_CONFIG_PATH;
}

export function loadAiConnectionTestConfig():
  | AiConnectionTestConfig
  | undefined {
  const configPath = getAiConnectionTestConfigPath();
  if (!existsSync(configPath)) {
    return undefined;
  }

  try {
    const parsed = JSON.parse(readFileSync(configPath, 'utf-8')) as unknown;
    return parseConfig(parsed) ?? undefined;
  } catch {
    return undefined;
  }
}

export function toStoredAiConnectionState(
  config: AiConnectionTestConfig,
): StoredAiConnectionState {
  return {
    llmProvider: config.llmProvider,
    providerSettings: {
      [config.llmProvider]: {
        llmApiBaseUrl: config.llmApiBaseUrl,
        llmModel: config.llmModel,
        llmApiKey: config.llmApiKey,
      },
    },
    mcpEnabled: config.mcpEnabled,
    mcpServerUrl: config.mcpServerUrl,
    mcpBearerToken: config.mcpBearerToken,
    agentMaxIterations: config.agentMaxIterations,
    systemPrompt: config.systemPrompt,
  };
}

/**
 * Seed the global AI connection config via the backend API.
 *
 * Runs inside the authenticated browser context so it reuses the logged-in
 * session cookie (the user must hold the AIConnectionConfig write permission,
 * e.g. admin).
 */
export async function applyAiConnectionTestConfig(page: Page): Promise<boolean> {
  const config = loadAiConnectionTestConfig();
  if (!config) {
    return false;
  }

  const stored = toStoredAiConnectionState(config);
  const ok = await page.evaluate(
    async ({ endpoint, value }) => {
      const csrfResponse = await fetch('/api/v1/security/csrf_token/', {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
      });
      const csrfJson = (await csrfResponse.json()) as { result?: string };
      const response = await fetch(endpoint, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfJson.result ?? '',
        },
        credentials: 'same-origin',
        body: JSON.stringify(value),
      });
      return response.ok;
    },
    { endpoint: AI_CONNECTION_ENDPOINT, value: stored },
  );
  return ok;
}
