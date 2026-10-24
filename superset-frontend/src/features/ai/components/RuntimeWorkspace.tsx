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
import { v4 as uuidv4 } from 'uuid';
import { styled } from '@apache-superset/core/theme';
import { t } from '@apache-superset/core/translation';
import { Button, Input, Select, Tag } from '@superset-ui/core/components';
import { Icons } from '@superset-ui/core/components/Icons';
import { Alert } from '@apache-superset/core/components';
import { makeUrl } from 'src/utils/pathUtils';
import {
  createChatSession,
  ChatSessionRequestError,
  getChatSessionByUuid,
  listChatSessions,
} from '../aiChatSessionApi';
import { ChatSession, ChatSessionSummary, AiChatChartPayload } from '../types';
import {
  Artifact,
  RuntimeContext,
  RuntimeMetadata,
  Turn,
  isTerminal,
  reduceTurn,
  TurnEvent,
  runtimeGet,
  runtimePost,
} from '../runtime';
import ChatMarkdown from './ChatMarkdown';
import ChatHistoryItem from './ChatHistoryItem';
import ReplyActions from './ReplyActions';
import WorkActivity from './WorkActivity';
import UserMessage from './UserMessage';
import ChatComposer, { ImageDraft } from './ChatComposer';
import ChatChartEmbed from './ChatChartEmbed';
import { rewriteSupersetExploreUrl } from '../supersetUrlUtils';

const Workspace = styled.div<{
  $historyWidth: number;
  $historyCollapsed: boolean;
  $artifactWidth: number;
}>`
  display: grid;
  --history-pane-width: ${({ $historyWidth, $historyCollapsed }) =>
    $historyCollapsed
      ? '56px'
      : `min(${$historyWidth}px, 40vw, calc(100% - 620px))`};
  grid-template-columns:
    var(--history-pane-width) minmax(320px, 1fr)
    clamp(
      300px,
      ${({ $artifactWidth }) => $artifactWidth}px,
      calc(100% - var(--history-pane-width) - 320px)
    );
  height: calc(100dvh - 64px);
  background: ${({ theme }) => theme.colorBgContainer};
  color: ${({ theme }) => theme.colorText};
  > aside,
  > main {
    min-width: 0;
    overflow: auto;
    padding: 20px;
  }
  > aside[data-pane='artifacts'] {
    position: relative;
    display: flex;
    min-height: 0;
    overflow: visible;
    padding: 0;
  }
  .artifact-content {
    flex: 1;
    min-width: 0;
    overflow: auto;
    padding: 20px;
  }
  > aside {
    background: ${({ theme }) => theme.colorBgLayout};
  }
  > main {
    display: flex;
    flex-direction: column;
  }
  h2 {
    font-size: 20px;
  }
  h3 {
    font-size: 16px;
  }
  > nav {
    display: none;
  }
  button {
    white-space: normal;
  }
  > aside[data-pane='history'] {
    position: sticky;
    top: 0;
    align-self: start;
    height: calc(100dvh - 64px);
    display: flex;
    flex-direction: column;
    overflow: visible;
    padding: 0;
    min-height: 0;
  }
  .history-header {
    display: flex;
    flex-shrink: 0;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 12px;
    h2 {
      margin: 0;
    }
  }
  .history-actions {
    flex-shrink: 0;
    padding: 0 12px 12px;
    button {
      width: 100%;
    }
  }
  .history-content {
    flex: 1;
    min-height: 0;
    padding: 0 12px 20px;
    overflow: auto;
    overflow-x: hidden;
  }
  .history-content button {
    width: 100%;
    min-height: 36px;
    text-align: left;
  }
  .history-toggle {
    flex-shrink: 0;
  }
  @media (min-width: 651px) {
    &[data-history-collapsed='true'] {
      .history-header {
        padding-inline: 4px;
      }
      .history-header h2,
      .history-actions,
      .history-content,
      .history-resize {
        display: none;
      }
    }
  }
  @media (max-width: 1100px) {
    .artifact-resize {
      display: none;
    }
    grid-template-columns:
      ${({ $historyWidth, $historyCollapsed }) =>
        $historyCollapsed ? '56px' : `min(${$historyWidth}px, 40vw)`}
      minmax(320px, 1fr);
    > aside:last-child {
      grid-column: 2;
    }
    height: auto;
    min-height: calc(100vh - 48px);
  }
  @media (max-width: 650px) {
    display: flex;
    flex-direction: column;
    > aside[data-pane='history'] {
      position: relative;
      align-self: stretch;
      height: calc(100dvh - 120px);
    }
    > nav {
      display: flex;
      gap: 8px;
      padding: 12px;
    }
    .history-toggle,
    .history-resize {
      display: none;
    }
    &[data-section='chat'] > [data-pane]:not([data-pane='chat']),
    &[data-section='history'] > [data-pane]:not([data-pane='history']),
    &[data-section='artifacts'] > [data-pane]:not([data-pane='artifacts']) {
      display: none;
    }
  }
`;
const HistoryResizeHandle = styled.div`
  position: absolute;
  z-index: 1;
  top: 0;
  right: -4px;
  bottom: 0;
  width: 8px;
  cursor: col-resize;
  touch-action: none;
  &:hover,
  &:focus-visible {
    background: ${({ theme }) => theme.colorPrimaryBg};
    outline: 1px solid ${({ theme }) => theme.colorPrimary};
  }
`;
const ArtifactResizeHandle = styled(HistoryResizeHandle)`
  right: auto;
  left: -4px;
  &::after {
    content: '';
    position: absolute;
    top: 0;
    bottom: 0;
    left: 4px;
    width: 1px;
    background: ${({ theme }) => theme.colorBorderSecondary};
  }
`;
const HistoryButton = styled(Button)`
  &&& {
    display: flex;
    justify-content: flex-start;
    min-width: 0;
    height: 36px;
    margin: 2px 0;
    padding: 0 8px;
    border: 0;
    box-shadow: none;
    color: ${({ theme }) => theme.colorText};
    background: transparent;
    &:hover {
      background: ${({ theme }) => theme.colorFillTertiary};
    }
    &[aria-current='page'] {
      background: ${({ theme }) => theme.colorFillSecondary};
    }
    > span {
      display: block;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
`;
const Conversation = styled.div`
  flex: 1;
  min-width: 0;
  min-height: 220px;
  overflow: auto;
  padding: 24px 8px;
  article {
    width: 100%;
    max-width: 768px;
    margin: 0 auto 32px;
  }
  article[data-role='user'] {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    .message-body {
      width: fit-content;
      max-width: 80%;
      padding: 12px 16px;
      border-radius: ${({ theme }) => theme.sizeUnit * 6}px;
      background: ${({ theme }) => theme.colorPrimaryBg};
      color: ${({ theme }) => theme.colorText};
    }
  }
  article[data-role='assistant'] .message-body p {
    margin-bottom: 16px;
    &:last-child {
      margin-bottom: 0;
    }
  }
  @media (max-width: 650px) {
    padding: 20px 0;
    article[data-role='user'] .message-body {
      max-width: 90%;
    }
  }
`;
const Controls = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0;
  align-items: center;
  > .ant-select {
    min-width: 140px;
  }
`;
const ArtifactBody = styled.section`
  margin: 20px 0;
  overflow-wrap: anywhere;
  pre {
    white-space: pre-wrap;
  }
`;

function ArtifactView({ artifact }: { artifact: Artifact }) {
  const chart = artifact.payload.chart ?? artifact.payload;
  const nativeChart =
    artifact.provenance?.connection_id === 'focalbi' ||
    String(artifact.provenance?.tool ?? '').startsWith('focalbi__');
  return (
    <ArtifactBody id={`artifact-${artifact.id}`} tabIndex={-1}>
      <h3>{artifact.title}</h3>
      <Tag>{artifact.saved ? t('Saved') : t('Preview')}</Tag>{' '}
      <span>{t('Version %s', artifact.version)}</span>
      {artifact.type === 'chart' &&
      nativeChart &&
      typeof chart === 'object' &&
      chart &&
      'viz_type' in chart ? (
        <ChatChartEmbed
          chart={{
            ...(chart as AiChatChartPayload),
            id: artifact.id,
            title: artifact.title,
            ...(typeof (chart as Record<string, unknown>).id === 'number'
              ? { slice_id: (chart as Record<string, unknown>).id as number }
              : {}),
            ...((chart as AiChatChartPayload).form_data?.datasource
              ? { slice_id: undefined }
              : {}),
          }}
        />
      ) : artifact.type === 'table' && Array.isArray(artifact.payload.rows) ? (
        <div style={{ overflowX: 'auto' }}>
          <table aria-label={artifact.title}>
            <thead>
              <tr>
                {Object.keys(
                  artifact.payload.rows[0] &&
                    typeof artifact.payload.rows[0] === 'object'
                    ? artifact.payload.rows[0]
                    : { value: '' },
                ).map(column => (
                  <th key={column} scope="col">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(artifact.payload.rows as unknown[])
                .slice(0, 100)
                .map((row, index) => (
                  <tr key={index}>
                    {Object.values(
                      row && typeof row === 'object' ? row : { value: row },
                    ).map((cell, column) => (
                      <td key={column}>
                        {typeof cell === 'object'
                          ? JSON.stringify(cell)
                          : String(cell ?? '')}
                      </td>
                    ))}
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      ) : artifact.type === 'source' &&
        typeof artifact.payload.url === 'string' &&
        /^(https?:\/\/|\/(?!\/))/.test(artifact.payload.url) ? (
        <a
          href={
            nativeChart
              ? rewriteSupersetExploreUrl(artifact.payload.url)
              : artifact.payload.url
          }
          target="_blank"
          rel="noopener noreferrer"
        >
          {artifact.title}
        </a>
      ) : (
        <pre>{JSON.stringify(artifact.payload, null, 2)}</pre>
      )}
      {artifact.provenance && (
        <details>
          <summary>{t('Sources and provenance')}</summary>
          <pre>{JSON.stringify(artifact.provenance, null, 2)}</pre>
        </details>
      )}
    </ArtifactBody>
  );
}

export default function RuntimeWorkspace({
  metadata,
}: {
  metadata: RuntimeMetadata;
}) {
  const history = useHistory();
  const { sessionId } = useParams<{ sessionId?: string }>();
  const selected = useRef(sessionId);
  selected.current = sessionId;
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [session, setSession] = useState<ChatSession | null>(null);
  const [turn, setTurn] = useState<Turn | null>(null);
  const [input, setInput] = useState('');
  const [activityDisclosure, setActivityDisclosure] = useState<
    Record<string, boolean>
  >({});
  const [modelId, setModelId] = useState(
    metadata.models?.find(m => m.default)?.id ?? '',
  );
  const [images, setImages] = useState<ImageDraft[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [historyWidth, setHistoryWidth] = useState(240);
  const [historyCollapsed, setHistoryCollapsed] = useState(false);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const [artifactWidth, setArtifactWidth] = useState(() =>
    Math.max(300, Math.min(960, Math.round(window.innerWidth * 0.38))),
  );
  const [artifactMaxWidth, setArtifactMaxWidth] = useState(960);
  const artifactDrag = useRef<{ x: number; width: number } | null>(null);
  const resizeArtifact = (width: number) =>
    setArtifactWidth(Math.max(300, Math.min(artifactMaxWidth, width)));
  useEffect(() => {
    const workspace = workspaceRef.current;
    const historyPane = workspace?.querySelector('[data-pane="history"]');
    if (!workspace || !historyPane) return undefined;
    const observer = new ResizeObserver(() => {
      if (window.innerWidth <= 1100) return;
      const max = Math.max(
        300,
        Math.min(
          960,
          Math.floor(
            workspace.clientWidth -
              historyPane.getBoundingClientRect().width -
              320,
          ),
        ),
      );
      setArtifactMaxWidth(max);
      setArtifactWidth(width => Math.min(width, max));
    });
    observer.observe(workspace);
    observer.observe(historyPane);
    return () => observer.disconnect();
  }, []);
  const historyDrag = useRef<{ x: number; width: number } | null>(null);
  const resizeHistory = (width: number) =>
    setHistoryWidth(Math.max(180, Math.min(520, width)));
  const [section, setSection] = useState<'chat' | 'history' | 'artifacts'>(
    'chat',
  );
  const [workflows, setWorkflows] = useState<string[]>([]);
  const [context, setContext] = useState<RuntimeContext[]>([]);
  const [contextType, setContextType] =
    useState<RuntimeContext['type']>('dataset');
  const [contextId, setContextId] = useState('');
  const [filters, setFilters] = useState('{}');
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const report = useCallback(
    (reason: unknown) =>
      setError(
        reason instanceof Error
          ? reason.message
          : t('Request failed. Try again.'),
      ),
    [],
  );
  const refresh = useCallback(
    async () => setSessions(await listChatSessions()),
    [],
  );
  useEffect(() => {
    refresh().catch(report);
  }, [refresh, report]);
  useEffect(() => {
    let disposed = false;
    setTurn(null);
    setSession(null);
    setError('');
    setImages([]);
    setInput('');
    setModelId(metadata.models?.find(m => m.default)?.id ?? '');
    if (sessionId)
      getChatSessionByUuid(sessionId)
        .then(async value => {
          if (disposed) return;
          setSession(value);
          setModelId(
            value.modelId ?? metadata.models?.find(m => m.default)?.id ?? '',
          );
          const current = value.activeTurn ?? value.latestTurn;
          if (current) {
            const active = await runtimeGet<Turn>(`turns/${current.id}`);
            if (!disposed) setTurn(active);
          }
        })
        .catch(reason => {
          if (disposed) return;
          if (
            reason instanceof ChatSessionRequestError &&
            (reason.status === 403 || reason.status === 404)
          ) {
            history.replace('/ai/');
          } else report(reason);
        });
    return () => {
      disposed = true;
    };
  }, [sessionId, report, history]);
  const running = Boolean(turn && !isTerminal(turn));
  const replyPersisted = Boolean(
    turn &&
    session?.messages.some(
      message =>
        message.runtimeTurnId === turn.id && message.role === 'assistant',
    ),
  );
  // Poll authoritative snapshots so refresh/reconnect never depends on client memory.
  useEffect(() => {
    if (!turn || isTerminal(turn)) return undefined;
    let disposed = false;
    const timer = setInterval(() => {
      runtimeGet<Turn>(`turns/${turn.id}`)
        .then(value => {
          if (disposed) return;
          setTurn(previous =>
            !previous ||
            previous.id !== value.id ||
            value.last_sequence < previous.last_sequence
              ? previous
              : value,
          );
          if (isTerminal(value)) {
            getChatSessionByUuid(value.thread_id)
              .then(value => {
                if (selected.current === value.id) setSession(value);
              })
              .catch(report);
            refresh().catch(report);
          }
        })
        .catch(report);
    }, 1000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [turn?.id, running, refresh, report]);
  useEffect(() => {
    if (!turn || isTerminal(turn) || typeof EventSource === 'undefined')
      return undefined;
    const source = new EventSource(
      makeUrl(`/api/v1/ai/turns/${turn.id}/events?after=${turn.last_sequence}`),
    );
    const receive = (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as TurnEvent;
        setTurn(previous => reduceTurn(previous, data));
      } catch {
        /* Authoritative polling recovers malformed or interrupted streams. */
      }
    };
    source.onmessage = receive;
    [
      'status',
      'message_delta',
      'tool_started',
      'tool_completed',
      'activity_updated',
      'artifact',
      'request',
      'usage',
      'turn_completed',
      'turn_failed',
    ].forEach(type => source.addEventListener(type, receive as EventListener));
    return () => source.close();
  }, [turn?.id, running]);
  const perform = async (action: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (reason) {
      report(reason);
    } finally {
      setBusy(false);
    }
  };
  const send = () =>
    perform(async () => {
      if (!input.trim() && !images.length) return;
      if (running && turn) {
        setTurn(
          await runtimePost<Turn>(`turns/${turn.id}/input`, {
            idempotency_key: uuidv4(),
            expected_turn_id: turn.id,
            input,
          }),
        );
      } else {
        const target = session ?? (await createChatSession(input.slice(0, 80)));
        if (!session) {
          setSession(target);
        }
        const value = await runtimePost<Turn>(`threads/${target.id}/turns`, {
          input: input.trim() || t('Describe the attached image.'),
          model_id: modelId,
          attachment_ids: images.flatMap(image =>
            image.image ? [image.image.id] : [],
          ),
          context,
          workflow_ids: workflows,
          idempotency_key: uuidv4(),
        });
        setTurn(value);
        setSession(await getChatSessionByUuid(target.id));
        await refresh();
        if (!sessionId) history.replace(`/ai/${target.id}`);
      }
      setInput('');
      images.forEach(image => URL.revokeObjectURL(image.preview));
      setImages([]);
    });
  const openBranch = async (
    turnId: string,
    mode: 'retry' | 'after' | 'edit',
    editedInput?: string,
  ) => {
    if (!session) throw new Error(t('Conversation is unavailable.'));
    const result = await runtimePost<{ uuid: string }>(
      `threads/${session.id}/fork`,
      {
        turn_id: turnId,
        mode,
        model_id: modelId,
        ...(mode === 'edit' ? { input: editedInput } : {}),
      },
    );
    history.push(`/ai/${result.uuid}`);
  };
  const fork = (turnId: string, mode: 'retry' | 'after') =>
    perform(() => openBranch(turnId, mode));
  const resendEdited = async (turnId: string, editedInput: string) => {
    setBusy(true);
    try {
      await openBranch(turnId, 'edit', editedInput);
    } finally {
      setBusy(false);
    }
  };
  const artifacts = Array.from(
    new Map(
      [
        ...(session?.messages.flatMap(message => message.artifacts ?? []) ??
          []),
        ...(turn?.artifacts ?? []),
      ].map(artifact => [artifact.id, artifact]),
    ).values(),
  );
  const inspectArtifact = (id: string) => {
    setSection('artifacts');
    requestAnimationFrame(() =>
      document.getElementById(`artifact-${id}`)?.focus(),
    );
  };
  return (
    <Workspace
      ref={workspaceRef}
      data-section={section}
      data-history-collapsed={historyCollapsed}
      $historyWidth={historyWidth}
      $historyCollapsed={historyCollapsed}
      $artifactWidth={artifactWidth}
    >
      <nav aria-label={t('Chat workspace sections')}>
        <Button
          buttonStyle={section === 'history' ? 'primary' : 'secondary'}
          aria-pressed={section === 'history'}
          onClick={() => setSection('history')}
        >
          {t('History')}
        </Button>
        <Button
          buttonStyle={section === 'chat' ? 'primary' : 'secondary'}
          aria-pressed={section === 'chat'}
          onClick={() => setSection('chat')}
        >
          {t('Chat')}
        </Button>
        <Button
          buttonStyle={section === 'artifacts' ? 'primary' : 'secondary'}
          aria-pressed={section === 'artifacts'}
          onClick={() => setSection('artifacts')}
        >
          {t('Artifacts')}
        </Button>
      </nav>
      <aside data-pane="history" aria-label={t('Chat history')}>
        <div className="history-header">
          <h2>{t('AI Chat')}</h2>
          <Button
            className="history-toggle"
            buttonStyle="tertiary"
            aria-label={
              historyCollapsed ? t('Expand sidebar') : t('Collapse sidebar')
            }
            title={
              historyCollapsed ? t('Expand sidebar') : t('Collapse sidebar')
            }
            aria-expanded={!historyCollapsed}
            aria-controls="ai-chat-history-list"
            onClick={() => setHistoryCollapsed(value => !value)}
          >
            <Icons.RightOutlined
              style={{
                transform: historyCollapsed ? undefined : 'rotate(180deg)',
              }}
            />
          </Button>
        </div>
        <div className="history-actions">
          <HistoryButton
            data-action="new-chat"
            buttonStyle="tertiary"
            aria-label={t('New chat')}
            icon={<Icons.EditOutlined aria-hidden />}
            onClick={() => history.push('/ai/')}
          >
            {t('New chat')}
          </HistoryButton>
        </div>
        <div className="history-content" id="ai-chat-history-list">
          {sessions.map(item => (
            <ChatHistoryItem
              key={item.id}
              item={item}
              selected={sessionId === item.id}
              onSelect={() => {
                history.push(`/ai/${item.id}`);
                setSection('chat');
              }}
              onUpdated={updated => {
                setSessions(values =>
                  values
                    .map(value => (value.id === updated.id ? updated : value))
                    .sort(
                      (a, b) =>
                        Number(Boolean(b.isPinned)) -
                          Number(Boolean(a.isPinned)) ||
                        b.updatedAt - a.updatedAt,
                    ),
                );
                setSession(value =>
                  value?.id === updated.id ? { ...value, ...updated } : value,
                );
              }}
              onDeleted={() => {
                setSessions(values =>
                  values.filter(value => value.id !== item.id),
                );
                if (selected.current === item.id) history.push('/ai/');
              }}
              onError={report}
            />
          ))}
        </div>
        <HistoryResizeHandle
          className="history-resize"
          role="separator"
          aria-label={t('Resize chat sidebar')}
          aria-orientation="vertical"
          aria-valuemin={180}
          aria-valuemax={520}
          aria-valuenow={historyWidth}
          tabIndex={0}
          onKeyDown={event => {
            if (
              ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)
            ) {
              event.preventDefault();
              resizeHistory(
                event.key === 'Home'
                  ? 180
                  : event.key === 'End'
                    ? 520
                    : historyWidth + (event.key === 'ArrowRight' ? 20 : -20),
              );
            }
          }}
          onPointerDown={event => {
            if (event.button !== 0) return;
            event.preventDefault();
            historyDrag.current = { x: event.clientX, width: historyWidth };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={event => {
            if (historyDrag.current)
              resizeHistory(
                historyDrag.current.width +
                  event.clientX -
                  historyDrag.current.x,
              );
          }}
          onPointerUp={event => {
            historyDrag.current = null;
            event.currentTarget.releasePointerCapture(event.pointerId);
          }}
          onLostPointerCapture={() => {
            historyDrag.current = null;
          }}
        />
      </aside>
      <main data-pane="chat">
        <h2>{session?.title ?? t('Explore your data')}</h2>
        {metadata.post && (
          <div>
            <Tag>{t('Post: %s', metadata.post.name)}</Tag>
          </div>
        )}
        {error && (
          <Alert
            type="error"
            message={error}
            closable
            onClose={() => setError('')}
          />
        )}
        <Conversation aria-live="polite">
          {!session?.messages.length && !turn && (
            <p>
              {t(
                'Ask a question, attach data context, or build a chart. Your conversation and work are saved automatically.',
              )}
            </p>
          )}
          {session?.messages.map(message => (
            <article
              key={message.id}
              data-role={message.role}
              aria-label={
                message.role === 'user'
                  ? t('Your message')
                  : t('Assistant reply')
              }
            >
              {message.role === 'user' ? (
                <UserMessage
                  content={message.content}
                  attachments={message.attachments}
                  disabled={busy || running}
                  onResend={
                    message.runtimeTurnId
                      ? value => resendEdited(message.runtimeTurnId!, value)
                      : undefined
                  }
                  onError={report}
                />
              ) : (
                <div className="message-body">
                  {message.role === 'assistant' && (
                    <WorkActivity
                      openOverride={
                        message.runtimeTurnId
                          ? activityDisclosure[message.runtimeTurnId]
                          : undefined
                      }
                      onOpenChange={open => {
                        if (message.runtimeTurnId)
                          setActivityDisclosure(previous => ({
                            ...previous,
                            [message.runtimeTurnId!]: open,
                          }));
                      }}
                      activity={
                        message.activity ??
                        (message.runtimeTurnId === turn?.id
                          ? turn?.activity
                          : undefined)
                      }
                    />
                  )}
                  <ChatMarkdown content={message.content} />
                </div>
              )}
              {Boolean(message.artifacts?.length) && (
                <Controls>
                  {message.artifacts?.map(artifact => (
                    <Button
                      key={artifact.id}
                      buttonStyle="secondary"
                      onClick={() => inspectArtifact(artifact.id)}
                    >
                      {t('Inspect %s', artifact.title)}
                    </Button>
                  ))}
                </Controls>
              )}
              {message.charts?.map(chart => (
                <ChatChartEmbed key={chart.id} chart={chart} />
              ))}
              {message.role === 'assistant' && (
                <ReplyActions
                  content={message.content}
                  disabled={busy || running}
                  onRetry={
                    message.runtimeTurnId
                      ? () => fork(message.runtimeTurnId!, 'retry')
                      : undefined
                  }
                  onFork={
                    message.runtimeTurnId
                      ? () => fork(message.runtimeTurnId!, 'after')
                      : undefined
                  }
                  onError={report}
                />
              )}
            </article>
          ))}
          {turn &&
            (!replyPersisted ||
              turn.error ||
              turn.pending_requests.length > 0) && (
              <article data-role="assistant" aria-label={t('Current turn')}>
                {turn.status !== 'completed' && <Tag>{turn.status}</Tag>}
                {!session?.messages.some(
                  message =>
                    message.runtimeTurnId === turn.id &&
                    message.role === 'assistant',
                ) && (
                  <>
                    <WorkActivity
                      key={turn.id}
                      activity={turn.activity}
                      openOverride={activityDisclosure[turn.id]}
                      onOpenChange={open =>
                        setActivityDisclosure(previous => ({
                          ...previous,
                          [turn.id]: open,
                        }))
                      }
                    />
                    <div className="message-body">
                      <ChatMarkdown content={turn.content} />
                    </div>
                    {Boolean(turn.artifacts.length) && (
                      <Controls>
                        {turn.artifacts.map(artifact => (
                          <Button
                            key={artifact.id}
                            buttonStyle="secondary"
                            onClick={() => inspectArtifact(artifact.id)}
                          >
                            {t('Inspect %s', artifact.title)}
                          </Button>
                        ))}
                      </Controls>
                    )}
                  </>
                )}
                {turn.error && (
                  <Alert
                    type="error"
                    message={
                      typeof turn.error === 'string'
                        ? turn.error
                        : turn.error.message
                    }
                  />
                )}
                {turn.pending_requests.map(request => (
                  <section key={request.id}>
                    <h3>
                      {request.kind === 'approval'
                        ? t('Approval required')
                        : request.kind === 'review'
                          ? t('Inspect the previous operation')
                          : request.kind === 'connection'
                            ? t('Service needs administrator attention')
                            : t('A question for you')}
                    </h3>
                    <p>{request.message}</p>
                    {request.tool && <p>{t('Operation: %s', request.tool)}</p>}
                    {request.arguments && (
                      <pre>{JSON.stringify(request.arguments, null, 2)}</pre>
                    )}
                    {request.schema && (
                      <p>
                        {t(
                          'Provide the requested fields as a JSON object: %s',
                          JSON.stringify(request.schema),
                        )}
                      </p>
                    )}
                    {request.scope && <p>{request.scope}</p>}
                    {request.expires_at && (
                      <p>{t('Expires: %s', request.expires_at)}</p>
                    )}
                    {request.kind === 'clarification' && (
                      <Input
                        aria-label={request.message}
                        value={answers[request.id] ?? ''}
                        onChange={event =>
                          setAnswers({
                            ...answers,
                            [request.id]: event.target.value,
                          })
                        }
                      />
                    )}
                    {(request.kind === 'approval'
                      ? ['accept', 'decline']
                      : request.kind === 'review'
                        ? []
                        : request.kind === 'connection'
                          ? ['relinked']
                          : [answers[request.id] ?? '']
                    ).map(decision => (
                      <Button
                        key={decision}
                        disabled={busy || !decision}
                        onClick={() =>
                          perform(async () => {
                            setTurn(
                              await runtimePost<Turn>(
                                `turns/${turn.id}/input`,
                                {
                                  idempotency_key: uuidv4(),
                                  expected_turn_id: turn.id,
                                  request_id: request.id,
                                  response:
                                    request.kind === 'approval'
                                      ? { decision }
                                      : { input: decision },
                                },
                              ),
                            );
                          })
                        }
                      >
                        {request.kind === 'approval'
                          ? decision === 'accept'
                            ? t('Approve')
                            : t('Decline')
                          : request.kind === 'connection'
                            ? t('Resume after administrator repair')
                            : t('Submit answer')}
                      </Button>
                    ))}
                  </section>
                ))}
                {!running &&
                  !session?.messages.some(
                    message =>
                      message.runtimeTurnId === turn.id &&
                      message.role === 'assistant',
                  ) && (
                    <ReplyActions
                      content={turn.content}
                      disabled={busy}
                      onRetry={() => fork(turn.id, 'retry')}
                      onFork={
                        turn.status === 'completed'
                          ? () => fork(turn.id, 'after')
                          : undefined
                      }
                      onError={report}
                    />
                  )}
              </article>
            )}
        </Conversation>
        <details>
          <summary>{t('Context and tools')}</summary>
          <Controls>
            <Select
              aria-label={t('Context type')}
              value={contextType}
              options={['dataset', 'chart', 'dashboard'].map(value => ({
                value,
                label: value,
              }))}
              onChange={value =>
                setContextType(value as RuntimeContext['type'])
              }
            />
            <Input
              aria-label={t('Context ID')}
              placeholder={t('ID')}
              value={contextId}
              onChange={event => setContextId(event.target.value)}
            />
            <Input
              aria-label={t('Filters JSON')}
              placeholder={t('Filters (JSON)')}
              value={filters}
              onChange={event => setFilters(event.target.value)}
            />
            <Button
              buttonStyle="secondary"
              onClick={() => {
                try {
                  const parsed = JSON.parse(filters);
                  if (
                    !Number.isSafeInteger(Number(contextId)) ||
                    Number(contextId) <= 0 ||
                    !parsed ||
                    Array.isArray(parsed) ||
                    typeof parsed !== 'object'
                  )
                    throw new Error(
                      t('Enter a positive ID and a JSON object for filters.'),
                    );
                  setContext([
                    ...context,
                    {
                      type: contextType,
                      id: Number(contextId),
                      filters: parsed,
                    },
                  ]);
                  setContextId('');
                } catch (reason) {
                  report(reason);
                }
              }}
            >
              {t('Attach context')}
            </Button>
          </Controls>
          <Controls>
            <Select
              aria-label={t('Workflows')}
              mode="multiple"
              placeholder={t('Workflows')}
              value={workflows}
              options={metadata.workflows.map(value => ({
                value: value.id,
                label: value.name,
              }))}
              onChange={value => setWorkflows(value as string[])}
            />
          </Controls>
        </details>
        <Controls>
          {context.map((value, index) => (
            <Tag
              key={`${value.type}-${value.id}-${index}`}
              closable
              onClose={() => setContext(context.filter((_, i) => i !== index))}
            >
              {value.type} #{value.id} {JSON.stringify(value.filters)}
            </Tag>
          ))}
        </Controls>
        <ChatComposer
          value={input}
          onChange={setInput}
          models={metadata.models ?? []}
          modelId={modelId}
          onModelChange={setModelId}
          images={images}
          onImagesChange={setImages}
          imageLimits={metadata.image_limits ?? { count: 4, bytes: 5242880 }}
          retainedImageCount={
            new Set(
              session?.messages.flatMap(
                m => m.attachments?.map(i => i.id) ?? [],
              ),
            ).size
          }
          busy={busy}
          running={running}
          onSend={send}
          onError={report}
          onStop={() => {
            if (turn)
              perform(async () => {
                setTurn(await runtimePost<Turn>(`turns/${turn.id}/cancel`, {}));
              });
          }}
        />
      </main>
      <aside data-pane="artifacts" aria-label={t('Artifacts')}>
        <ArtifactResizeHandle
          className="artifact-resize"
          role="separator"
          aria-label={t('Resize artifacts pane')}
          aria-orientation="vertical"
          aria-controls="ai-chat-artifacts"
          aria-valuemin={300}
          aria-valuemax={artifactMaxWidth}
          aria-valuenow={artifactWidth}
          tabIndex={0}
          onKeyDown={event => {
            if (
              ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)
            ) {
              event.preventDefault();
              resizeArtifact(
                event.key === 'Home'
                  ? 300
                  : event.key === 'End'
                    ? artifactMaxWidth
                    : artifactWidth + (event.key === 'ArrowLeft' ? 20 : -20),
              );
            }
          }}
          onPointerDown={event => {
            if (event.button !== 0) return;
            event.preventDefault();
            artifactDrag.current = { x: event.clientX, width: artifactWidth };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={event => {
            if (artifactDrag.current)
              resizeArtifact(
                artifactDrag.current.width +
                  artifactDrag.current.x -
                  event.clientX,
              );
          }}
          onPointerUp={event => {
            artifactDrag.current = null;
            event.currentTarget.releasePointerCapture(event.pointerId);
          }}
          onLostPointerCapture={() => {
            artifactDrag.current = null;
          }}
        />
        <div className="artifact-content" id="ai-chat-artifacts">
          <h2>{t('Artifacts')}</h2>
          {artifacts.length ? (
            artifacts.map(artifact => (
              <ArtifactView key={artifact.id} artifact={artifact} />
            ))
          ) : (
            <p>{t('Charts, queries and results appear here as you work.')}</p>
          )}
        </div>
      </aside>
    </Workspace>
  );
}
