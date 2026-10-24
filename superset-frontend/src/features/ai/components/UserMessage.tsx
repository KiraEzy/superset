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
import { useState } from 'react';
import { styled } from '@apache-superset/core/theme';
import { t } from '@apache-superset/core/translation';
import { Alert } from '@apache-superset/core/components';
import { Button, Input } from '@superset-ui/core/components';
import { Icons } from '@superset-ui/core/components/Icons';
import copyTextToClipboard from 'src/utils/copy';
import ChatMarkdown from './ChatMarkdown';

const Actions = styled.div`
  display: flex;
  gap: 2px;
  margin: 2px -6px 0 0;
`;
const IconButton = styled(Button)`
  &&& {
    width: 28px;
    min-width: 28px;
    height: 28px;
    margin: 0;
    padding: 0;
    border: 0;
    box-shadow: none;
    background: transparent;
    color: ${({ theme }) => theme.colorTextSecondary};
    &:hover {
      background: ${({ theme }) => theme.colorFillTertiary};
    }
    @media (pointer: coarse) {
      width: 36px;
      min-width: 36px;
      height: 36px;
    }
  }
`;
const Editor = styled.div`
  width: 100%;
  padding: 12px;
  border-radius: ${({ theme }) => theme.sizeUnit * 5}px;
  background: ${({ theme }) => theme.colorFillTertiary};
  .edit-note {
    margin: 8px 0;
    color: ${({ theme }) => theme.colorTextSecondary};
    font-size: ${({ theme }) => theme.fontSizeSM}px;
  }
  .edit-controls {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 8px;
  }
`;
const EditInput = styled(Input.TextArea)`
  &&& {
    border: 0;
    box-shadow: none;
    background: transparent;
    resize: none;
  }
`;

export default function UserMessage({
  content,
  attachments,
  disabled,
  onResend,
  onError,
}: {
  content: string;
  attachments?: import('../runtime').ImageReference[];
  disabled?: boolean;
  onResend?: (input: string) => Promise<void>;
  onError: (error: unknown) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(content);
  const [sending, setSending] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');
  const resend = async () => {
    if (!onResend || sending || disabled || !draft.trim()) return;
    setSending(true);
    setError('');
    try {
      await onResend(draft.trim());
      setEditing(false);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : t('Could not resend the message. Try again.'),
      );
    } finally {
      setSending(false);
    }
  };
  if (editing)
    return (
      <Editor>
        {error && <Alert type="error" message={error} />}
        <EditInput
          aria-label={t('Edit message')}
          autoFocus
          value={draft}
          disabled={sending}
          maxLength={64000}
          autoSize={{ minRows: 2, maxRows: 10 }}
          onChange={event => setDraft(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
              event.preventDefault();
              resend();
            } else if (event.key === 'Escape' && !sending) setEditing(false);
          }}
        />
        <p className="edit-note">
          {t(
            'Starts a new branch from this message. Later messages are omitted; saved BI resources remain.',
          )}
        </p>
        <div className="edit-controls">
          <Button
            buttonStyle="secondary"
            disabled={sending}
            onClick={() => setEditing(false)}
          >
            {t('Cancel')}
          </Button>
          <Button
            buttonStyle="primary"
            disabled={sending || disabled || !draft.trim()}
            onClick={resend}
          >
            {sending ? t('Sending…') : t('Send')}
          </Button>
        </div>
      </Editor>
    );
  return (
    <>
      <div className="message-body">
        {attachments?.map(image => (
          <a key={image.id} href={image.url} target="_blank" rel="noreferrer">
            <img
              src={image.url}
              alt={image.name}
              style={{
                maxWidth: 160,
                maxHeight: 120,
                objectFit: 'contain',
                borderRadius: 12,
                margin: 4,
              }}
            />
          </a>
        ))}
        <ChatMarkdown content={content} />
      </div>
      <Actions role="group" aria-label={t('Message actions')}>
        <IconButton
          buttonStyle="tertiary"
          aria-label={copied ? t('Copied') : t('Copy message')}
          title={copied ? t('Copied') : t('Copy message')}
          onBlur={() => setCopied(false)}
          onClick={async () => {
            try {
              await copyTextToClipboard(() => Promise.resolve(content));
              setCopied(true);
            } catch (reason) {
              onError(reason);
            }
          }}
        >
          {copied ? (
            <Icons.CheckOutlined aria-hidden />
          ) : (
            <Icons.CopyOutlined aria-hidden />
          )}
        </IconButton>
        <IconButton
          buttonStyle="tertiary"
          aria-label={t('Edit message')}
          title={t('Edit message')}
          disabled={disabled || !onResend}
          onClick={() => {
            setDraft(content);
            setError('');
            setEditing(true);
          }}
        >
          <Icons.EditOutlined aria-hidden />
        </IconButton>
      </Actions>
    </>
  );
}
