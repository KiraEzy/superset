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
import {
  formatAiChatError,
  streamChatMessage,
} from 'src/features/ai/aiChatApi';
import {
  appendChatMessage,
  createChatSession,
  deleteChatSession,
  generateSessionTitle,
  getChatSessionByUuid,
  listChatSessions,
  updateChatSessionTitle,
} from 'src/features/ai/aiChatSessionApi';
import {
  ChatMessage,
  ChatSession,
  ChatSessionSummary,
  AiChatChartPayload,
} from 'src/features/ai/types';

function createLocalId(): string {
  return `local-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function sortSummariesByRecency(
  summaries: ChatSessionSummary[],
): ChatSessionSummary[] {
  return [...summaries].sort((a, b) => b.updatedAt - a.updatedAt);
}

/** Insert or re-sort when recency increases (e.g. user sent a message). */
function bumpSessionSummary(
  summaries: ChatSessionSummary[],
  summary: ChatSessionSummary,
): ChatSessionSummary[] {
  const without = summaries.filter(item => item.id !== summary.id);
  return sortSummariesByRecency([summary, ...without]);
}

/** Update metadata without changing sidebar order (e.g. session selected). */
function mergeSessionSummaryInPlace(
  summaries: ChatSessionSummary[],
  summary: ChatSessionSummary,
): ChatSessionSummary[] {
  const index = summaries.findIndex(item => item.id === summary.id);
  if (index === -1) {
    return sortSummariesByRecency([...summaries, summary]);
  }
  return summaries.map(item =>
    item.id === summary.id ? { ...item, ...summary } : item,
  );
}

function isAbortError(error: unknown): boolean {
  if (!error || typeof error !== 'object') {
    return false;
  }
  const err = error as {
    name?: string;
    statusText?: string;
    originalError?: { name?: string; statusText?: string };
  };
  return (
    err.name === 'AbortError' ||
    err.statusText === 'abort' ||
    err.originalError?.name === 'AbortError' ||
    err.originalError?.statusText === 'abort'
  );
}

function computeResponseDurationSeconds(startedAtMs: number): number {
  return Math.max(0, Math.round((Date.now() - startedAtMs) / 1000));
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
  const abortControllerRef = useRef<AbortController | null>(null);
  const streamedContentRef = useRef('');
  const chartsThisTurnRef = useRef<AiChatChartPayload[]>([]);
  const activeStreamMetaRef = useRef<{
    sessionId: string;
    assistantLocalId: string;
  } | null>(null);

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

  useEffect(
    () => () => {
      abortControllerRef.current?.abort();
    },
    [],
  );

  useEffect(() => {
    abortControllerRef.current?.abort();
  }, [urlSessionId]);

  useEffect(() => {
    if (!urlSessionId) {
      setActiveSession(null);
      activeSessionRef.current = null;
      return;
    }

    // Session already loaded locally (e.g. created mid-send from /ai/); refetch would
    // overwrite optimistic messages with an empty server snapshot.
    if (activeSessionRef.current?.id === urlSessionId) {
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
        setSessions(prev => mergeSessionSummaryInPlace(prev, session));
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
      setSessions(prev => bumpSessionSummary(prev, session));
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

  const stopGeneration = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  const deleteSession = useCallback(
    async (sessionId: string) => {
      try {
        if (
          activeSessionRef.current?.id === sessionId &&
          abortControllerRef.current
        ) {
          abortControllerRef.current.abort();
        }
        await deleteChatSession(sessionId);
        setSessions(prev => prev.filter(s => s.id !== sessionId));
        if (activeSessionRef.current?.id === sessionId) {
          setActiveSession(null);
          history.replace('/ai/');
        }
      } catch (error) {
        showError(error);
      }
    },
    [history, showError],
  );

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isSending) {
        return;
      }

      setIsSending(true);
      let session = activeSessionRef.current;
      let streamStartedAt = 0;

      try {
        if (!session) {
          session = await createChatSession(t('New chat'));
          setSessions(prev => bumpSessionSummary(prev, session!));
          activeSessionRef.current = session;
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
          const base =
            prev?.id === session!.id ? prev : { ...session!, messages: [] };
          return {
            ...base,
            title: nextTitle,
            updatedAt: Date.now(),
            messages: [
              ...base.messages,
              optimisticUserMessage,
              optimisticAssistant,
            ],
          };
        });

        const { message: persistedUser, session: userSessionSummary } =
          await appendChatMessage(session.id, {
            role: 'user',
            content: trimmed,
          });

        if (userSessionSummary) {
          setSessions(prev => bumpSessionSummary(prev, userSessionSummary));
        }

        if (isFirstMessage && nextTitle !== session.title) {
          const updatedSummary = await updateChatSessionTitle(
            session.id,
            nextTitle,
          );
          setSessions(prev => mergeSessionSummaryInPlace(prev, updatedSummary));
        }

        setActiveSession(prev => {
          const base =
            prev?.id === session!.id ? prev : { ...session!, messages: [] };
          return {
            ...base,
            title: nextTitle,
            messages: base.messages.map(msg =>
              msg.id === optimisticUserMessage.id ? persistedUser : msg,
            ),
          };
        });

        streamedContentRef.current = '';
        chartsThisTurnRef.current = [];
        const controller = new AbortController();
        abortControllerRef.current = controller;
        activeStreamMetaRef.current = {
          sessionId: session.id,
          assistantLocalId,
        };

        streamStartedAt = Date.now();
        let streamedContent = '';
        const response = await streamChatMessage(
          historyForLlm,
          {
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
              streamedContentRef.current = streamedContent;
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
            onChart: chart => {
              chartsThisTurnRef.current = [...chartsThisTurnRef.current, chart];
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
                          charts: [...(msg.charts ?? []), chart],
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
          },
          controller.signal,
        );

        const durationSeconds = computeResponseDurationSeconds(streamStartedAt);

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
                    streaming: false,
                    status: undefined,
                    durationSeconds,
                  }
                : msg,
            ),
          };
        });

        let assistantContent = response.content;
        if (response.tools_used?.length) {
          assistantContent += `\n\n—\n_${t('Tools used')}: ${response.tools_used.join(', ')}_`;
        }

        const assistantExtra: Record<string, unknown> = {
          duration_seconds: durationSeconds,
        };
        if (response.tools_used?.length) {
          assistantExtra.tools_used = response.tools_used;
        }
        if (response.charts?.length) {
          assistantExtra.charts = response.charts;
        }

        const { message: persistedAssistant, session: updatedSummary } =
          await appendChatMessage(session.id, {
            role: 'assistant',
            content: assistantContent,
            extra: assistantExtra,
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
          setSessions(prev => mergeSessionSummaryInPlace(prev, updatedSummary));
        } else {
          await refreshSessionList();
        }
      } catch (error) {
        if (isAbortError(error) && session) {
          const partialContent = streamedContentRef.current.trim();
          const streamMeta = activeStreamMetaRef.current;
          const durationSeconds =
            computeResponseDurationSeconds(streamStartedAt);

          if (partialContent && streamMeta?.sessionId === session.id) {
            try {
              const abortExtra: Record<string, unknown> = {
                stopped: true,
                duration_seconds: durationSeconds,
              };
              if (chartsThisTurnRef.current.length) {
                abortExtra.charts = chartsThisTurnRef.current;
              }
              const { message: persistedAssistant, session: updatedSummary } =
                await appendChatMessage(session.id, {
                  role: 'assistant',
                  content: partialContent,
                  extra: abortExtra,
                });

              setActiveSession(prev => {
                if (!prev || prev.id !== session!.id) {
                  return prev;
                }
                return {
                  ...prev,
                  updatedAt: Date.now(),
                  messages: prev.messages.map(msg =>
                    msg.id === streamMeta.assistantLocalId
                      ? persistedAssistant
                      : msg,
                  ),
                };
              });

              if (updatedSummary) {
                setSessions(prev =>
                  mergeSessionSummaryInPlace(prev, updatedSummary),
                );
              }
            } catch (persistError) {
              showError(persistError);
            }
          } else if (streamMeta?.sessionId === session.id) {
            setActiveSession(prev => {
              if (!prev || prev.id !== session!.id) {
                return prev;
              }
              return {
                ...prev,
                messages: prev.messages.filter(
                  msg => msg.id !== streamMeta.assistantLocalId,
                ),
              };
            });
          }
        } else {
          showError(error);
          if (session) {
            const durationSeconds =
              streamStartedAt > 0
                ? computeResponseDurationSeconds(streamStartedAt)
                : undefined;
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
                        ...(durationSeconds !== undefined
                          ? { durationSeconds }
                          : {}),
                      }
                    : msg,
                ),
              };
            });
          }
        }
      } finally {
        abortControllerRef.current = null;
        activeStreamMetaRef.current = null;
        streamedContentRef.current = '';
        chartsThisTurnRef.current = [];
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
    stopGeneration,
    deleteSession,
  };
}
