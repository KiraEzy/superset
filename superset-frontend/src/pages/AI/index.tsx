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
import { useState, useRef, useEffect, useCallback, KeyboardEvent } from 'react';
import { t } from '@apache-superset/core/translation';
import { styled, css } from '@apache-superset/core/theme';
import { DeleteModal, Loading } from '@superset-ui/core/components';
import { Icons } from '@superset-ui/core/components/Icons';
import ChatMarkdown from 'src/features/ai/components/ChatMarkdown';
import ChatChartEmbed from 'src/features/ai/components/ChatChartEmbed';
import { useAiChatSessions } from 'src/features/ai/hooks/useAiChatSessions';
import { ChatSessionSummary } from 'src/features/ai/types';

const PageWrapper = styled.div`
  display: flex;
  height: calc(100vh - 48px);
  overflow: hidden;
`;

const Sidebar = styled.aside`
  ${({ theme }) => css`
    width: 260px;
    min-width: 260px;
    background: ${theme.colorBgLayout};
    border-right: 1px solid ${theme.colorBorderSecondary};
    display: flex;
    flex-direction: column;
    height: 100%;
  `}
`;

const SidebarHeader = styled.div`
  ${({ theme }) => css`
    padding: ${theme.sizeUnit * 3}px;
    display: flex;
    flex-direction: column;
    gap: ${theme.sizeUnit * 2}px;
  `}
`;

const NewChatButton = styled.button`
  ${({ theme }) => css`
    display: flex;
    align-items: center;
    justify-content: center;
    gap: ${theme.sizeUnit * 2}px;
    width: 100%;
    padding: ${theme.sizeUnit * 2.5}px ${theme.sizeUnit * 3}px;
    border: 1px solid ${theme.colorBorderSecondary};
    border-radius: ${theme.borderRadiusLG}px;
    background: ${theme.colorBgContainer};
    color: ${theme.colorText};
    font-size: ${theme.fontSize}px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      background: ${theme.colorBgTextHover};
    }
  `}
`;

const SidebarTabs = styled.div`
  ${({ theme }) => css`
    display: flex;
    padding: 0 ${theme.sizeUnit * 3}px;
    gap: ${theme.sizeUnit}px;
    border-bottom: 1px solid ${theme.colorBorderSecondary};
  `}
`;

const SidebarTab = styled.button<{ active?: boolean }>`
  ${({ theme, active }) => css`
    flex: 1;
    padding: ${theme.sizeUnit * 2}px 0;
    border: none;
    background: none;
    color: ${active ? theme.colorPrimary : theme.colorTextSecondary};
    font-size: ${theme.fontSizeSM}px;
    font-weight: ${active ? 600 : 400};
    cursor: pointer;
    border-bottom: 2px solid ${active ? theme.colorPrimary : 'transparent'};
    transition: all 0.2s;

    &:hover {
      color: ${theme.colorPrimary};
    }
  `}
`;

const SessionList = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: ${({ theme }) => theme.sizeUnit * 2}px;
`;

const SessionItemRow = styled.div`
  ${({ theme }) => css`
    display: flex;
    align-items: center;
    gap: ${theme.sizeUnit}px;
    border-radius: ${theme.borderRadiusLG}px;

    &:hover {
      background: ${theme.colorBgTextHover};

      button[data-delete-session] {
        opacity: 1;
      }
    }
  `}
`;

const SessionItem = styled.button<{ active?: boolean }>`
  ${({ theme, active }) => css`
    display: flex;
    align-items: center;
    gap: ${theme.sizeUnit * 2}px;
    flex: 1;
    min-width: 0;
    padding: ${theme.sizeUnit * 2}px ${theme.sizeUnit * 2.5}px;
    border: none;
    border-radius: ${theme.borderRadiusLG}px;
    background: ${active ? theme.colorBgTextHover : 'transparent'};
    color: ${theme.colorText};
    font-size: ${theme.fontSizeSM}px;
    text-align: left;
    cursor: pointer;
    transition: background 0.15s;

    &:hover {
      background: transparent;
    }
  `}
`;

const SessionTitle = styled.span`
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const SessionDeleteButton = styled.button`
  ${({ theme }) => css`
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    width: 28px;
    height: 28px;
    margin-right: ${theme.sizeUnit}px;
    border: none;
    border-radius: ${theme.borderRadius}px;
    background: transparent;
    color: ${theme.colorTextSecondary};
    cursor: pointer;
    opacity: 0;
    transition: opacity 0.15s, color 0.15s;

    &:hover {
      color: ${theme.colorError};
      background: ${theme.colorErrorBg};
    }
  `}
`;

const MainArea = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: ${({ theme }) => theme.colorBgContainer};
`;

const MessagesContainer = styled.div`
  ${({ theme }) => css`
    flex: 1;
    overflow-y: auto;
    padding: ${theme.sizeUnit * 4}px;
    display: flex;
    flex-direction: column;
    gap: ${theme.sizeUnit * 4}px;
  `}
`;

const EmptyState = styled.div`
  ${({ theme }) => css`
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: ${theme.sizeUnit * 3}px;
    color: ${theme.colorTextSecondary};
  `}
`;

const EmptyTitle = styled.h2`
  ${({ theme }) => css`
    margin: 0;
    font-size: ${theme.fontSizeHeading3}px;
    font-weight: 600;
    color: ${theme.colorText};
  `}
`;

const EmptySubtitle = styled.p`
  ${({ theme }) => css`
    margin: 0;
    font-size: ${theme.fontSize}px;
    color: ${theme.colorTextSecondary};
  `}
`;

const MessageRow = styled.div<{ role: 'user' | 'assistant' }>`
  ${({ theme, role }) => css`
    display: flex;
    justify-content: ${role === 'user' ? 'flex-end' : 'flex-start'};
    max-width: 768px;
    width: 100%;
    margin: 0 auto;
  `}
`;

const StatusText = styled.div`
  ${({ theme }) => css`
    font-size: ${theme.fontSizeSM}px;
    color: ${theme.colorTextSecondary};
    font-style: italic;
    margin-bottom: ${theme.sizeUnit}px;
  `}
`;

const ResponseDuration = styled.div`
  ${({ theme }) => css`
    margin-top: ${theme.sizeUnit * 2}px;
    font-size: ${theme.fontSizeSM - 1}px;
    color: ${theme.colorTextTertiary};
    text-align: right;
  `}
`;

const MessageBubble = styled.div<{ role: 'user' | 'assistant'; error?: boolean }>`
  ${({ theme, role, error }) => css`
    max-width: ${role === 'assistant' ? '90%' : '80%'};
    padding: ${theme.sizeUnit * 2.5}px ${theme.sizeUnit * 3.5}px;
    border-radius: ${theme.borderRadiusLG}px;
    font-size: ${theme.fontSize}px;
    line-height: 1.6;
    word-break: break-word;

    ${
      error
        ? css`
            background: ${theme.colorErrorBg};
            color: ${theme.colorErrorText};
            border: 1px solid ${theme.colorErrorBorder};
            border-bottom-left-radius: ${theme.borderRadiusSM}px;
          `
        : role === 'user'
          ? css`
              background: ${theme.colorPrimary};
              color: #fff;
              border-bottom-right-radius: ${theme.borderRadiusSM}px;
              white-space: pre-wrap;
            `
          : css`
              background: ${theme.colorBgLayout};
              color: ${theme.colorText};
              border-bottom-left-radius: ${theme.borderRadiusSM}px;
            `
    }
  `}
`;

const InputArea = styled.div`
  ${({ theme }) => css`
    padding: ${theme.sizeUnit * 3}px ${theme.sizeUnit * 4}px
      ${theme.sizeUnit * 4}px;
    max-width: 768px;
    width: 100%;
    margin: 0 auto;
  `}
`;

const InputWrapper = styled.div`
  ${({ theme }) => css`
    display: flex;
    align-items: flex-end;
    gap: ${theme.sizeUnit * 2}px;
    padding: ${theme.sizeUnit * 2}px;
    border: 1px solid ${theme.colorBorderSecondary};
    border-radius: ${theme.borderRadiusLG}px;
    background: ${theme.colorBgContainer};
    transition: border-color 0.2s;

    &:focus-within {
      border-color: ${theme.colorPrimary};
    }
  `}
`;

const ChatTextarea = styled.textarea`
  ${({ theme }) => css`
    flex: 1;
    border: none;
    outline: none;
    resize: none;
    background: transparent;
    font-size: ${theme.fontSize}px;
    line-height: 1.5;
    color: ${theme.colorText};
    max-height: 150px;
    min-height: 24px;
    font-family: inherit;

    &::placeholder {
      color: ${theme.colorTextPlaceholder};
    }
  `}
`;

const SendButton = styled.button<{ disabled?: boolean }>`
  ${({ theme, disabled }) => css`
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border: none;
    border-radius: ${theme.borderRadius}px;
    background: ${disabled ? theme.colorBgTextHover : theme.colorPrimary};
    color: ${disabled ? theme.colorTextDisabled : '#fff'};
    cursor: ${disabled ? 'not-allowed' : 'pointer'};
    flex-shrink: 0;
    transition: background 0.2s;

    &:hover:not(:disabled) {
      opacity: 0.85;
    }
  `}
`;

const StopButton = styled.button`
  ${({ theme }) => css`
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border: none;
    border-radius: ${theme.borderRadius}px;
    background: ${theme.colorBgTextHover};
    color: ${theme.colorText};
    cursor: pointer;
    flex-shrink: 0;
    transition: background 0.2s;

    &:hover {
      background: ${theme.colorErrorBg};
      color: ${theme.colorError};
    }
  `}
`;

const LoadingWrapper = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
`;

export default function AI() {
  const {
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
  } = useAiChatSessions();

  const [sidebarTab, setSidebarTab] = useState<'history'>('history');
  const [sessionToDelete, setSessionToDelete] =
    useState<ChatSessionSummary | null>(null);
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [activeSession?.messages.length, scrollToBottom]);

  const handleSend = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || isSending) {
      return;
    }
    setInputValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    await sendMessage(text);
  }, [inputValue, isSending, sendMessage]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTextareaInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 150)}px`;
  };

  const activeSessionId = activeSession?.id ?? null;
  const showEmptyState =
    !isLoadingSession &&
    (!activeSession || activeSession.messages.length === 0);

  const handleConfirmDelete = useCallback(async () => {
    if (!sessionToDelete) {
      return;
    }
    const { id } = sessionToDelete;
    setSessionToDelete(null);
    await deleteSession(id);
  }, [deleteSession, sessionToDelete]);

  return (
    <PageWrapper>
      <Sidebar>
        <SidebarHeader>
          <NewChatButton onClick={createNewSession}>
            <Icons.PlusOutlined iconSize="s" />
            {t('New chat')}
          </NewChatButton>
        </SidebarHeader>

        <SidebarTabs>
          <SidebarTab
            active={sidebarTab === 'history'}
            onClick={() => setSidebarTab('history')}
          >
            {t('History')}
          </SidebarTab>
        </SidebarTabs>

        <SessionList>
          {isLoadingSessions && (
            <EmptySubtitle style={{ textAlign: 'center', padding: '24px 0' }}>
              {t('Loading...')}
            </EmptySubtitle>
          )}
          {!isLoadingSessions && sessions.length === 0 && (
            <EmptySubtitle style={{ textAlign: 'center', padding: '24px 0' }}>
              {t('No conversations yet')}
            </EmptySubtitle>
          )}
          {sessions.map(session => (
            <SessionItemRow key={session.id}>
              <SessionItem
                active={session.id === activeSessionId}
                onClick={() => selectSession(session.id)}
              >
                <Icons.CommentOutlined iconSize="s" />
                <SessionTitle>{session.title}</SessionTitle>
              </SessionItem>
              <SessionDeleteButton
                type="button"
                data-delete-session
                aria-label={t('Delete conversation')}
                onClick={e => {
                  e.stopPropagation();
                  setSessionToDelete(session);
                }}
              >
                <Icons.DeleteOutlined iconSize="s" />
              </SessionDeleteButton>
            </SessionItemRow>
          ))}
        </SessionList>
      </Sidebar>

      {sessionToDelete && (
        <DeleteModal
          open
          title={t('Delete conversation?')}
          description={t(
            'This will permanently delete "%s".',
            sessionToDelete.title,
          )}
          onConfirm={handleConfirmDelete}
          onHide={() => setSessionToDelete(null)}
        />
      )}

      <MainArea>
        {isLoadingSession ? (
          <LoadingWrapper>
            <Loading />
          </LoadingWrapper>
        ) : showEmptyState ? (
          <EmptyState>
            <EmptyTitle>{t('What can I help you with?')}</EmptyTitle>
            <EmptySubtitle>
              {t(
                'Ask questions about your data, create charts, or explore dashboards.',
              )}
            </EmptySubtitle>
          </EmptyState>
        ) : (
          <MessagesContainer>
            {activeSession?.messages.map(msg => (
              <MessageRow key={msg.id} role={msg.role}>
                <MessageBubble role={msg.role} error={msg.error}>
                  {msg.status && <StatusText>{msg.status}</StatusText>}
                  {msg.role === 'assistant' &&
                    msg.charts?.map(chart => (
                      <ChatChartEmbed key={chart.id} chart={chart} />
                    ))}
                  {msg.role === 'assistant' && msg.content ? (
                    <ChatMarkdown content={msg.content} />
                  ) : (
                    msg.content
                  )}
                  {msg.streaming && !msg.content && !msg.status && '...'}
                  {msg.role === 'assistant' &&
                    msg.durationSeconds !== undefined &&
                    !msg.streaming && (
                      <ResponseDuration>
                        {t('%s sec', msg.durationSeconds)}
                      </ResponseDuration>
                    )}
                </MessageBubble>
              </MessageRow>
            ))}
            <div ref={messagesEndRef} />
          </MessagesContainer>
        )}

        <InputArea>
          <InputWrapper>
            <ChatTextarea
              ref={textareaRef}
              rows={1}
              value={inputValue}
              onChange={handleTextareaInput}
              onKeyDown={handleKeyDown}
              placeholder={t('Message AI...')}
            />
            {isSending ? (
              <StopButton
                type="button"
                aria-label={t('Stop generating')}
                onClick={stopGeneration}
              >
                <Icons.StopOutlined iconSize="s" />
              </StopButton>
            ) : (
              <SendButton
                disabled={!inputValue.trim()}
                onClick={handleSend}
              >
                <Icons.CaretRightOutlined iconSize="s" />
              </SendButton>
            )}
          </InputWrapper>
        </InputArea>
      </MainArea>
    </PageWrapper>
  );
}
