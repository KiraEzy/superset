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
import { useCallback, useEffect, useRef, useState } from 'react';
import { useHistory, useParams } from 'react-router-dom';
import { t } from '@apache-superset/core/translation';
import { addDangerToast } from 'src/components/MessageToasts/actions';
import { useDispatch } from 'react-redux';
import { getAiConnectionConfig } from 'src/features/ai/aiConnectionConfig';
import { formatAiChatError, streamChatMessage } from 'src/features/ai/aiChatApi';
import {
  appendChatMessage,
  createChatSession,
  generateSessionTitle,
  getChatSessionByUuid,
  listChatSessions,
  updateChatSessionTitle,
} from 'src/features/ai/aiChatSessionApi';
import { ChatMessage, ChatSession, ChatSessionSummary } from 'src/features/ai/types';

function createLocalId(): string {
  return `local-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function upsertSummary(
  summaries: ChatSessionSummary[],
  summary: ChatSessionSummary,
): ChatSessionSummary[] {
  const without = summaries.filter(item => item.id !== summary.id);
  return [summary, ...without].sort((a, b) => b.updatedAt - a.updatedAt);
}

export function useAiChatSessions() {
  const dispatch = useDispatch();
  const history = useHistory();
  const { sessionId: urlSessionId } = useParams<{ sessionId?: string }>();

  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [isLoadingSessions, setIsLoadingSessions] = useState(true);
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const activeSessionRef = useRef<ChatSession | null>(null);

  useEffect(() => {
    activeSessionRef.current = activeSession;
  }, [activeSession]);

  const showError = useCallback(
    (error: unknown) => {
      dispatch(addDangerToast(formatAiChatError(error)));
    },
    [dispatch],
  );

  const refreshSessionList = useCallback(async () => {
    const result = await listChatSessions();
    setSessions(result);
    return result;
  }, []);

  useEffect(() => {
    let cancelled = false;
    setIsLoadingSessions(true);
    refreshSessionList()
      .catch(showError)
      .finally(() => {
        if (!cancelled) {
          setIsLoadingSessions(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [refreshSessionList, showError]);

  useEffect(() => {
    if (!urlSessionId) {
      setActiveSession(null);
      return;
    }

    let cancelled = false;
    setIsLoadingSession(true);
    getChatSessionByUuid(urlSessionId)
      .then(session => {
        if (cancelled) {
          return;
        }
        setActiveSession(session);
        setSessions(prev => upsertSummary(prev, session));
      })
      .catch(error => {
        if (cancelled) {
          return;
        }
        showError(error);
        history.replace('/ai/');
        setActiveSession(null);
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingSession(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [history, showError, urlSessionId]);

  const createNewSession = useCallback(async () => {
    try {
      const session = await createChatSession(t('New chat'));
      setSessions(prev => upsertSummary(prev, session));
      setActiveSession(session);
      history.push(`/ai/${session.id}`);
    } catch (error) {
      showError(error);
    }
  }, [history, showError]);

  const selectSession = useCallback(
    (sessionId: string) => {
      history.push(`/ai/${sessionId}`);
    },
    [history],
  );

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isSending) {
        return;
      }

      setIsSending(true);
      let session = activeSessionRef.current;

      try {
        if (!session) {
          session = await createChatSession(t('New chat'));
          setSessions(prev => upsertSummary(prev, session!));
          setActiveSession(session);
          history.replace(`/ai/${session.id}`);
        }

        const isFirstMessage = session.messages.length === 0;
        const nextTitle = isFirstMessage
          ? generateSessionTitle(trimmed)
          : session.title;

        const optimisticUserMessage: ChatMessage = {
          id: createLocalId(),
          role: 'user',
          content: trimmed,
          timestamp: Date.now(),
        };

        const assistantLocalId = createLocalId();
        const optimisticAssistant: ChatMessage = {
          id: assistantLocalId,
          role: 'assistant',
          content: '',
          timestamp: Date.now(),
          streaming: true,
          status: t('Thinking...'),
        };

        const historyForLlm = [
          ...session.messages.map(msg => ({
            role: msg.role,
            content: msg.content,
          })),
          { role: 'user' as const, content: trimmed },
        ];

        setActiveSession(prev => {
          if (!prev || prev.id !== session!.id) {
            return prev;
          }
          return {
            ...prev,
            title: nextTitle,
            updatedAt: Date.now(),
            messages: [
              ...prev.messages,
              optimisticUserMessage,
              optimisticAssistant,
            ],
          };
        });

        const { message: persistedUser } = await appendChatMessage(session.id, {
          role: 'user',
          content: trimmed,
        });

        if (isFirstMessage && nextTitle !== session.title) {
          const updatedSummary = await updateChatSessionTitle(
            session.id,
            nextTitle,
          );
          setSessions(prev => upsertSummary(prev, updatedSummary));
        }

        setActiveSession(prev => {
          if (!prev || prev.id !== session!.id) {
            return prev;
          }
          return {
            ...prev,
            title: nextTitle,
            messages: prev.messages.map(msg =>
              msg.id === optimisticUserMessage.id ? persistedUser : msg,
            ),
          };
        });

        let streamedContent = '';
        const response = await streamChatMessage(historyForLlm, getAiConnectionConfig(), {
          onStatus: message => {
            setActiveSession(prev => {
              if (!prev || prev.id !== session!.id) {
                return prev;
              }
              return {
                ...prev,
                messages: prev.messages.map(msg =>
                  msg.id === assistantLocalId
                    ? { ...msg, status: message }
                    : msg,
                ),
              };
            });
          },
          onToken: token => {
            streamedContent += token;
            setActiveSession(prev => {
              if (!prev || prev.id !== session!.id) {
                return prev;
              }
              return {
                ...prev,
                messages: prev.messages.map(msg =>
                  msg.id === assistantLocalId
                    ? {
                        ...msg,
                        content: msg.content + token,
                        status: undefined,
                      }
                    : msg,
                ),
              };
            });
          },
          onError: () => {
            setActiveSession(prev => {
              if (!prev || prev.id !== session!.id) {
                return prev;
              }
              return {
                ...prev,
                messages: prev.messages.map(msg =>
                  msg.id === assistantLocalId
                    ? { ...msg, status: undefined }
                    : msg,
                ),
              };
            });
          },
        });

        let assistantContent = response.content;
        if (response.tools_used?.length) {
          assistantContent += `\n\n—\n_${t('Tools used')}: ${response.tools_used.join(', ')}_`;
        }

        const { message: persistedAssistant, session: updatedSummary } =
          await appendChatMessage(session.id, {
            role: 'assistant',
            content: assistantContent,
            extra: response.tools_used?.length
              ? { tools_used: response.tools_used }
              : undefined,
          });

        setActiveSession(prev => {
          if (!prev || prev.id !== session!.id) {
            return prev;
          }
          return {
            ...prev,
            title: nextTitle,
            updatedAt: Date.now(),
            messages: prev.messages.map(msg =>
              msg.id === assistantLocalId ? persistedAssistant : msg,
            ),
          };
        });

        if (updatedSummary) {
          setSessions(prev => upsertSummary(prev, updatedSummary));
        } else {
          await refreshSessionList();
        }
      } catch (error) {
        showError(error);
        if (session) {
          setActiveSession(prev => {
            if (!prev || prev.id !== session!.id) {
              return prev;
            }
            return {
              ...prev,
              messages: prev.messages.map(msg =>
                msg.streaming
                  ? {
                      ...msg,
                      content: `${t('Error')}: ${formatAiChatError(error)}`,
                      streaming: false,
                      status: undefined,
                      error: true,
                    }
                  : msg,
              ),
            };
          });
        }
      } finally {
        setIsSending(false);
      }
    },
    [history, isSending, refreshSessionList, showError],
  );

  return {
    sessions,
    activeSession,
    isLoadingSessions,
    isLoadingSession,
    isSending,
    createNewSession,
    selectSession,
    sendMessage,
  };
}
