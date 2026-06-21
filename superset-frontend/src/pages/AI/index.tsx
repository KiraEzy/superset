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
import { Icons } from '@superset-ui/core/components/Icons';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

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

const SessionItem = styled.button<{ active?: boolean }>`
  ${({ theme, active }) => css`
    display: flex;
    align-items: center;
    gap: ${theme.sizeUnit * 2}px;
    width: 100%;
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
      background: ${theme.colorBgTextHover};
    }
  `}
`;

const SessionTitle = styled.span`
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

const MessageBubble = styled.div<{ role: 'user' | 'assistant' }>`
  ${({ theme, role }) => css`
    max-width: 80%;
    padding: ${theme.sizeUnit * 2.5}px ${theme.sizeUnit * 3.5}px;
    border-radius: ${theme.borderRadiusLG}px;
    font-size: ${theme.fontSize}px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;

    ${
      role === 'user'
        ? css`
            background: ${theme.colorPrimary};
            color: #fff;
            border-bottom-right-radius: ${theme.borderRadiusSM}px;
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

function createId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function generateSessionTitle(firstMessage: string): string {
  const maxLen = 30;
  const trimmed = firstMessage.trim().replace(/\n/g, ' ');
  return trimmed.length > maxLen ? `${trimmed.slice(0, maxLen)}...` : trimmed;
}

const MOCK_RESPONSES = [
  "I can help you explore your data. What dataset would you like to analyze?",
  "Let me look into that for you. Could you provide more details about what you're looking for?",
  "That's a great question! Based on your dashboards, I can help you create a visualization for that.",
  "I'd recommend starting with a time-series chart for that kind of analysis. Want me to set one up?",
  "I can run that SQL query for you. Let me check the available databases first.",
];

export default function AI() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sidebarTab, setSidebarTab] = useState<'history'>('history');
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const activeSession = sessions.find(s => s.id === activeSessionId) ?? null;

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [activeSession?.messages.length, scrollToBottom]);

  const createNewSession = useCallback(() => {
    const session: ChatSession = {
      id: createId(),
      title: t('New chat'),
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    setSessions(prev => [session, ...prev]);
    setActiveSessionId(session.id);
    setInputValue('');
    textareaRef.current?.focus();
  }, []);

  const sendMessage = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || isLoading) return;

    let sessionId = activeSessionId;

    if (!sessionId) {
      const session: ChatSession = {
        id: createId(),
        title: t('New chat'),
        messages: [],
        createdAt: Date.now(),
        updatedAt: Date.now(),
      };
      setSessions(prev => [session, ...prev]);
      sessionId = session.id;
      setActiveSessionId(session.id);
    }

    const userMsg: ChatMessage = {
      id: createId(),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };

    setSessions(prev =>
      prev.map(s => {
        if (s.id !== sessionId) return s;
        const isFirst = s.messages.length === 0;
        return {
          ...s,
          title: isFirst ? generateSessionTitle(text) : s.title,
          messages: [...s.messages, userMsg],
          updatedAt: Date.now(),
        };
      }),
    );
    setInputValue('');
    setIsLoading(true);

    // Simulate assistant response
    await new Promise(resolve => {
      setTimeout(resolve, 800 + Math.random() * 1200);
    });

    const assistantMsg: ChatMessage = {
      id: createId(),
      role: 'assistant',
      content:
        MOCK_RESPONSES[Math.floor(Math.random() * MOCK_RESPONSES.length)],
      timestamp: Date.now(),
    };

    setSessions(prev =>
      prev.map(s =>
        s.id === sessionId
          ? { ...s, messages: [...s.messages, assistantMsg], updatedAt: Date.now() }
          : s,
      ),
    );
    setIsLoading(false);
  }, [inputValue, isLoading, activeSessionId]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleTextareaInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 150)}px`;
  };

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
          <SidebarTab active={sidebarTab === 'history'} onClick={() => setSidebarTab('history')}>
            {t('History')}
          </SidebarTab>
        </SidebarTabs>

        <SessionList>
          {sessions.length === 0 && (
            <EmptySubtitle style={{ textAlign: 'center', padding: '24px 0' }}>
              {t('No conversations yet')}
            </EmptySubtitle>
          )}
          {sessions.map(session => (
            <SessionItem
              key={session.id}
              active={session.id === activeSessionId}
              onClick={() => setActiveSessionId(session.id)}
            >
              <Icons.CommentOutlined iconSize="s" />
              <SessionTitle>{session.title}</SessionTitle>
            </SessionItem>
          ))}
        </SessionList>
      </Sidebar>

      <MainArea>
        {!activeSession || activeSession.messages.length === 0 ? (
          <EmptyState>
            <EmptyTitle>{t('What can I help you with?')}</EmptyTitle>
            <EmptySubtitle>
              {t('Ask questions about your data, create charts, or explore dashboards.')}
            </EmptySubtitle>
          </EmptyState>
        ) : (
          <MessagesContainer>
            {activeSession.messages.map(msg => (
              <MessageRow key={msg.id} role={msg.role}>
                <MessageBubble role={msg.role}>{msg.content}</MessageBubble>
              </MessageRow>
            ))}
            {isLoading && (
              <MessageRow role="assistant">
                <MessageBubble role="assistant">...</MessageBubble>
              </MessageRow>
            )}
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
            <SendButton
              disabled={!inputValue.trim() || isLoading}
              onClick={sendMessage}
            >
              <Icons.CaretRightOutlined iconSize="s" />
            </SendButton>
          </InputWrapper>
        </InputArea>
      </MainArea>
    </PageWrapper>
  );
}
