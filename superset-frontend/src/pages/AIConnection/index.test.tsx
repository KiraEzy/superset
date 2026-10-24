/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The ASF licenses this file to You under the Apache License, Version 2.0
 * (the "License"); you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing, software distributed
 * under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
 * CONDITIONS OF ANY KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations under the License.
 */
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from 'spec/helpers/testing-library';
import * as config from 'src/features/ai/aiConnectionConfig';
import AIConnection from './index';
import * as catalogue from 'src/features/ai/modelCatalog';

jest.mock('src/features/home/SubMenu', () => ({
  __esModule: true,
  default: () => <nav>AI Connection</nav>,
}));
jest.mock('src/components/MessageToasts/withToasts', () => {
  const toasts = { addSuccessToast: jest.fn(), addDangerToast: jest.fn() };
  return { useToasts: () => toasts };
});

beforeEach(() => {
  jest
    .spyOn(catalogue, 'catalogRequest')
    .mockResolvedValue({ connections: [], models: [] });
  jest
    .spyOn(config, 'fetchMcpAccessOptions')
    .mockResolvedValue({ roles: [], users: [], tools: [] });
});
afterEach(() => jest.restoreAllMocks());

test('settings cannot be saved or tested before the stored configuration loads', async () => {
  const pending: { resolve?: (state: config.StoredAiConnectionState) => void } =
    {};
  jest.spyOn(config, 'fetchAiConnectionState').mockImplementation(
    () =>
      new Promise(resolve => {
        pending.resolve = resolve;
      }),
  );
  render(<AIConnection />);
  expect(
    screen.getByText('Save MCP and agent settings', { exact: true }),
  ).not.toBeVisible();
  expect(
    screen.getByText('Test LLM connection', { exact: true }),
  ).not.toBeVisible();
  await act(async () =>
    pending.resolve?.({
      llmProvider: 'custom',
      providerSettings: {
        custom: {
          llmApiBaseUrl: 'https://model.example/v1',
          llmModel: 'configured-local-model',
          llmApiKey: 'masked-test-only',
        },
      },
      mcpEnabled: true,
      mcpServerUrl: 'https://bi.example/mcp',
      mcpBearerToken: '',
      agentMaxIterations: 120,
      systemPrompt: '',
    }),
  );
  expect(
    screen.getByText('Save MCP and agent settings', { exact: true }),
  ).toBeVisible();
  expect(screen.getByRole('textbox', { name: /Model$/ })).toHaveValue(
    'configured-local-model',
  );
});

test('failed settings load never exposes default values as a savable global configuration', async () => {
  jest
    .spyOn(config, 'fetchAiConnectionState')
    .mockRejectedValue(new Error('unavailable'));
  render(<AIConnection />);
  expect(
    await screen.findByText(
      'Saved settings could not load. Reload this page before making changes.',
    ),
  ).toBeVisible();
  expect(
    screen.getByText('Save MCP and agent settings', { exact: true }),
  ).not.toBeVisible();
  expect(
    screen.getByText('Test MCP connection', { exact: true }),
  ).not.toBeVisible();
});

test('saving shared settings cannot save an unverified LLM draft', async () => {
  const stored: config.StoredAiConnectionState = {
    llmProvider: 'custom',
    providerSettings: {
      custom: {
        llmApiBaseUrl: 'https://original.example/v1',
        llmModel: 'original',
        llmApiKey: '',
      },
    },
    mcpEnabled: true,
    mcpServerUrl: 'https://bi.example/mcp',
    mcpBearerToken: '',
    agentMaxIterations: 120,
    systemPrompt: '',
  };
  jest.spyOn(config, 'fetchAiConnectionState').mockResolvedValue(stored);
  const save = jest
    .spyOn(config, 'saveAiConnectionState')
    .mockResolvedValue(stored);
  render(<AIConnection />);
  const input = await screen.findByRole('textbox', { name: /Model$/ });
  await waitFor(() => expect(input).toHaveValue('original'));
  fireEvent.change(input, { target: { value: 'unverified-draft' } });
  fireEvent.blur(input);
  fireEvent.click(
    screen.getByRole('button', { name: 'Save MCP and agent settings' }),
  );
  await waitFor(() => expect(save).toHaveBeenCalled());
  expect(save.mock.calls[0][0].providerSettings.custom?.llmModel).toBe(
    'original',
  );
});

test('a later legacy settings response cannot overwrite the selected named connection', async () => {
  let resolveSettings:
    | ((state: config.StoredAiConnectionState) => void)
    | undefined;
  jest.spyOn(config, 'fetchAiConnectionState').mockImplementation(
    () =>
      new Promise(resolve => {
        resolveSettings = resolve;
      }),
  );
  jest.spyOn(catalogue, 'catalogRequest').mockResolvedValue({
    connections: [
      {
        id: 'named',
        label: 'Hosted',
        revision: 1,
        config: {
          llmProvider: 'openai',
          llmApiBaseUrl: 'https://named.example/v1',
          llmModel: 'named-model',
          llmApiKey: '',
          llmAdapter: 'responses',
        },
      },
    ],
    models: [
      {
        id: 'model',
        connection_id: 'named',
        default: true,
        published: true,
        position: 0,
        ready: true,
        name: 'named-model',
        connection: 'Hosted',
        vision: true,
        status: 'verified',
      },
    ],
  });
  render(<AIConnection />);
  await waitFor(() =>
    expect(screen.getByDisplayValue('Hosted')).toHaveValue('Hosted'),
  );
  await act(async () =>
    resolveSettings?.({
      llmProvider: 'custom',
      providerSettings: {
        custom: {
          llmApiBaseUrl: 'https://legacy.example/v1',
          llmModel: 'legacy',
          llmApiKey: '',
        },
      },
      mcpEnabled: true,
      mcpServerUrl: 'https://bi.example/mcp',
      mcpBearerToken: '',
      agentMaxIterations: 120,
      systemPrompt: '',
    }),
  );
  expect(screen.getByRole('textbox', { name: /Model$/ })).toHaveValue(
    'named-model',
  );
});

test('reasoning visibility saves independently without sending endpoint credentials', async () => {
  const stored: config.StoredAiConnectionState = {
    llmProvider: 'custom',
    providerSettings: {},
    mcpEnabled: false,
    mcpServerUrl: '',
    mcpBearerToken: '',
    agentMaxIterations: 120,
    systemPrompt: '',
  };
  jest.spyOn(config, 'fetchAiConnectionState').mockResolvedValue(stored);
  const data = {
    connections: [
      {
        id: 'local',
        label: 'GPUStack',
        revision: 1,
        config: {
          llmProvider: 'custom',
          llmApiBaseUrl: 'https://local.example/v1',
          llmModel: 'test',
          llmApiKey: 'masked-test-only',
          showModelReasoning: false,
        },
      },
    ],
    models: [
      {
        id: 'model',
        connection_id: 'local',
        default: true,
        published: true,
        position: 0,
        ready: true,
        name: 'test',
        connection: 'GPUStack',
        vision: false,
        status: 'verified',
      },
    ],
  };
  const request = jest
    .spyOn(catalogue, 'catalogRequest')
    .mockResolvedValue(data);
  render(<AIConnection />);
  const toggle = await screen.findByRole('switch', {
    name: 'Show model reasoning to users',
  });
  fireEvent.click(toggle);
  fireEvent.click(
    screen.getByRole('button', { name: 'Save reasoning display' }),
  );
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      'connections/local/reasoning-visibility',
      { showModelReasoning: true },
    ),
  );
});
