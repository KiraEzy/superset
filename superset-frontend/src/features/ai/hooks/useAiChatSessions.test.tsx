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
import { ReactNode } from 'react';
import { renderHook, act } from '@testing-library/react-hooks';
import { waitFor } from '@testing-library/dom';
import { Provider } from 'react-redux';
import { createStore } from 'redux';
import { MemoryRouter, Route } from 'react-router-dom';
import * as aiChatSessionApi from 'src/features/ai/aiChatSessionApi';
import * as aiChatApi from 'src/features/ai/aiChatApi';
import { ChatSession, ChatSessionSummary } from 'src/features/ai/types';
import { useAiChatSessions } from './useAiChatSessions';

const mockDispatch = jest.fn();
jest.mock('react-redux', () => ({
  ...jest.requireActual('react-redux'),
  useDispatch: () => mockDispatch,
}));

jest.mock('src/features/ai/aiConnectionConfig', () => ({
  getAiConnectionConfig: () => ({
    llmProvider: 'custom',
    llmApiBaseUrl: 'https://api.example.com/v1',
    llmApiKey: 'key',
    llmModel: 'model',
    mcpEnabled: false,
    mcpServerUrl: '',
    mcpBearerToken: '',
    agentMaxIterations: 120,
    systemPrompt: '',
  }),
}));

const sessionSummary: ChatSessionSummary = {
  id: 'session-uuid-1',
  dbId: 1,
  title: 'Test chat',
  createdAt: 1,
  updatedAt: 2,
};

const activeSession: ChatSession = {
  ...sessionSummary,
  messages: [],
};

function createWrapper(initialEntry = '/ai/session-uuid-1') {
  const store = createStore(() => ({}));
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <Provider store={store}>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Route path="/ai/:sessionId?">{children}</Route>
        </MemoryRouter>
      </Provider>
    );
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  jest
    .spyOn(aiChatSessionApi, 'listChatSessions')
    .mockResolvedValue([sessionSummary]);
  jest
    .spyOn(aiChatSessionApi, 'getChatSessionByUuid')
    .mockResolvedValue(activeSession);
  jest.spyOn(aiChatSessionApi, 'deleteChatSession').mockResolvedValue();
});

afterEach(() => {
  jest.restoreAllMocks();
});

// eslint-disable-next-line no-restricted-globals -- TODO: Migrate from describe blocks
describe('useAiChatSessions deleteSession', () => {
  test('removes session from list and navigates when deleting active session', async () => {
    const { result } = renderHook(() => useAiChatSessions(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.sessions).toHaveLength(1);
    });

    await act(async () => {
      await result.current.deleteSession('session-uuid-1');
    });

    expect(aiChatSessionApi.deleteChatSession).toHaveBeenCalledWith(
      'session-uuid-1',
    );
    expect(result.current.sessions).toHaveLength(0);
    expect(result.current.activeSession).toBeNull();
  });

  test('removes non-active session without clearing active session', async () => {
    const otherSummary: ChatSessionSummary = {
      id: 'session-uuid-2',
      dbId: 2,
      title: 'Other chat',
      createdAt: 3,
      updatedAt: 4,
    };
    jest
      .spyOn(aiChatSessionApi, 'listChatSessions')
      .mockResolvedValue([sessionSummary, otherSummary]);

    const { result } = renderHook(() => useAiChatSessions(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.sessions).toHaveLength(2);
    });

    await act(async () => {
      await result.current.deleteSession('session-uuid-2');
    });

    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.sessions[0].id).toBe('session-uuid-1');
    expect(result.current.activeSession?.id).toBe('session-uuid-1');
  });
});

// eslint-disable-next-line no-restricted-globals -- TODO: Migrate from describe blocks
describe('useAiChatSessions stopGeneration', () => {
  beforeEach(() => {
    jest
      .spyOn(aiChatSessionApi, 'updateChatSessionTitle')
      .mockResolvedValue(sessionSummary);
  });

  test('persists partial assistant content when stream is aborted', async () => {
    jest.spyOn(aiChatSessionApi, 'appendChatMessage').mockImplementation(
      async (_sessionId, message) => ({
        message: {
          id: message.role === 'user' ? 'user-1' : 'assistant-1',
          role: message.role,
          content: message.content,
          timestamp: Date.now(),
        },
        session: sessionSummary,
      }),
    );

    jest
      .spyOn(aiChatApi, 'streamChatMessage')
      .mockImplementation(async (_history, _config, handlers = {}) => {
        handlers.onToken?.('partial ');
        handlers.onToken?.('text');
        throw new DOMException('Aborted', 'AbortError');
      });

    const { result } = renderHook(() => useAiChatSessions(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.activeSession?.id).toBe('session-uuid-1');
    });

    await act(async () => {
      await result.current.sendMessage('hello');
    });

    await waitFor(() => {
      expect(result.current.isSending).toBe(false);
    });

    expect(aiChatSessionApi.appendChatMessage).toHaveBeenCalledWith(
      'session-uuid-1',
      expect.objectContaining({
        role: 'assistant',
        content: 'partial text',
        extra: { stopped: true },
      }),
    );
    expect(mockDispatch).not.toHaveBeenCalled();
  });

  test('removes assistant placeholder when aborted before tokens arrive', async () => {
    jest.spyOn(aiChatSessionApi, 'appendChatMessage').mockImplementation(
      async (_sessionId, message) => ({
        message: {
          id: 'user-1',
          role: message.role,
          content: message.content,
          timestamp: Date.now(),
        },
        session: sessionSummary,
      }),
    );

    jest
      .spyOn(aiChatApi, 'streamChatMessage')
      .mockRejectedValue(new DOMException('Aborted', 'AbortError'));

    const { result } = renderHook(() => useAiChatSessions(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.activeSession?.id).toBe('session-uuid-1');
    });

    await act(async () => {
      await result.current.sendMessage('hello');
    });

    await waitFor(() => {
      expect(result.current.isSending).toBe(false);
    });

    const assistantCalls = (
      aiChatSessionApi.appendChatMessage as jest.Mock
    ).mock.calls.filter(([, msg]) => msg.role === 'assistant');
    expect(assistantCalls).toHaveLength(0);
    expect(result.current.activeSession?.messages).toHaveLength(1);
    expect(result.current.activeSession?.messages[0].role).toBe('user');
    expect(mockDispatch).not.toHaveBeenCalled();
  });

  test('persists charts from stream in message extra', async () => {
    const chartPayload = {
      id: 'chart-0',
      viz_type: 'pie',
      form_data: { viz_type: 'pie', datasource: '1__table' },
      slice_id: 42,
    };

    jest.spyOn(aiChatSessionApi, 'appendChatMessage').mockImplementation(
      async (_sessionId, message) => ({
        message: {
          id: message.role === 'user' ? 'user-1' : 'assistant-1',
          role: message.role,
          content: message.content,
          timestamp: Date.now(),
          charts: (message.extra?.charts as typeof chartPayload[]) ?? undefined,
        },
        session: sessionSummary,
      }),
    );

    jest
      .spyOn(aiChatApi, 'streamChatMessage')
      .mockImplementation(async (_history, _config, handlers = {}) => {
        handlers.onChart?.(chartPayload);
        return {
          content: 'Chart ready',
          tools_used: ['generate_chart'],
          charts: [chartPayload],
        };
      });

    const { result } = renderHook(() => useAiChatSessions(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.activeSession?.id).toBe('session-uuid-1');
    });

    await act(async () => {
      await result.current.sendMessage('make a chart');
    });

    await waitFor(() => {
      expect(result.current.isSending).toBe(false);
    });

    expect(aiChatSessionApi.appendChatMessage).toHaveBeenCalledWith(
      'session-uuid-1',
      expect.objectContaining({
        role: 'assistant',
        extra: expect.objectContaining({
          charts: [chartPayload],
        }),
      }),
    );
  });
});
