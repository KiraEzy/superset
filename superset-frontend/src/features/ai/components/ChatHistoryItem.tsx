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
import { Button, Dropdown, Input, Modal } from '@superset-ui/core/components';
import { Alert } from '@apache-superset/core/components';
import { Icons } from '@superset-ui/core/components/Icons';
import { ChatSessionSummary } from '../types';
import {
  deleteChatSession,
  updateChatSessionPin,
  updateChatSessionTitle,
} from '../aiChatSessionApi';

const Row = styled.div`
  display: flex;
  align-items: center;
  min-width: 0;
  margin: 2px 0;
  border-radius: ${({ theme }) => theme.borderRadius}px;
  &[data-selected='true'] {
    background: ${({ theme }) => theme.colorFillSecondary};
  }
  .chat-menu-trigger {
    opacity: 0;
  }
  &:hover .chat-menu-trigger,
  &:focus-within .chat-menu-trigger,
  &[data-menu-open='true'] .chat-menu-trigger {
    opacity: 1;
  }
  @media (hover: none) {
    .chat-menu-trigger {
      opacity: 1;
    }
  }
`;
const TitleButton = styled(Button)`
  &&& {
    display: flex;
    justify-content: flex-start;
    flex: 1;
    min-width: 0;
    width: auto;
    height: 36px;
    padding: 0 8px;
    border: 0;
    box-shadow: none;
    background: transparent;
    color: ${({ theme }) => theme.colorText};
    margin: 0;
    &:hover,
    &:focus,
    &:active {
      background: transparent;
      color: ${({ theme }) => theme.colorText};
      box-shadow: none;
    }
    > span {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
`;
const MenuButton = styled(Button)`
  &&& {
    flex: 0 0 28px;
    width: 28px;
    min-width: 28px;
    height: 32px;
    margin: 0 4px 0 0;
    padding: 0;
    border: 0;
    box-shadow: none;
    background: transparent;
    color: ${({ theme }) => theme.colorText};
    &:hover,
    &:focus,
    &:active {
      background: transparent;
      color: ${({ theme }) => theme.colorText};
      box-shadow: none;
    }
  }
`;

export default function ChatHistoryItem({
  item,
  selected,
  onSelect,
  onUpdated,
  onDeleted,
  onError,
}: {
  item: ChatSessionSummary;
  selected: boolean;
  onSelect: () => void;
  onUpdated: (item: ChatSessionSummary) => void;
  onDeleted: () => void;
  onError: (error: unknown) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [dialog, setDialog] = useState<'rename' | 'delete' | null>(null);
  const [title, setTitle] = useState(item.title);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const save = async () => {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      if (dialog === 'rename')
        onUpdated(await updateChatSessionTitle(item.id, title.trim()));
      else if (dialog === 'delete') {
        await deleteChatSession(item.id);
        onDeleted();
      }
      setDialog(null);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : t('Request failed. Try again.'),
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Row data-selected={selected} data-menu-open={menuOpen}>
        <TitleButton
          buttonStyle="tertiary"
          title={item.title}
          aria-label={item.title}
          aria-current={selected ? 'page' : undefined}
          onClick={onSelect}
        >
          <span>{item.title}</span>
        </TitleButton>
        {item.isPinned && (
          <span title={t('Pinned')}>
            <Icons.PushpinFilled aria-label={t('Pinned')} iconSize="s" />
          </span>
        )}
        <Dropdown
          trigger={['click']}
          open={menuOpen}
          onOpenChange={setMenuOpen}
          menu={{
            onClick: () => setMenuOpen(false),
            items: [
              {
                key: 'pin',
                label: item.isPinned ? t('Unpin') : t('Pin'),
                icon: <Icons.PushpinOutlined />,
                disabled: busy,
                onClick: async () => {
                  setBusy(true);
                  try {
                    onUpdated(
                      await updateChatSessionPin(item.id, !item.isPinned),
                    );
                  } catch (reason) {
                    onError(reason);
                  } finally {
                    setBusy(false);
                  }
                },
              },
              {
                key: 'rename',
                label: t('Rename'),
                icon: <Icons.EditOutlined />,
                disabled: busy,
                onClick: () => {
                  setTitle(item.title);
                  setError('');
                  setDialog('rename');
                },
              },
              {
                key: 'delete',
                label: t('Delete'),
                danger: true,
                icon: <Icons.DeleteOutlined />,
                disabled: busy,
                onClick: () => {
                  setError('');
                  setDialog('delete');
                },
              },
            ],
          }}
        >
          <MenuButton
            className="chat-menu-trigger"
            buttonStyle="tertiary"
            aria-label={t('Options for %s', item.title)}
            title={t('Chat options')}
          >
            <Icons.EllipsisOutlined aria-hidden />
          </MenuButton>
        </Dropdown>
      </Row>
      {dialog && (
        <Modal
          show
          title={dialog === 'rename' ? t('Rename chat') : t('Delete chat?')}
          onHide={() => {
            if (!busy) setDialog(null);
          }}
          onHandledPrimaryAction={save}
          primaryButtonName={dialog === 'rename' ? t('Save') : t('Delete')}
          disablePrimaryButton={busy || (dialog === 'rename' && !title.trim())}
        >
          {error && <Alert type="error" message={error} />}
          {dialog === 'rename' ? (
            <Input
              aria-label={t('Chat title')}
              value={title}
              maxLength={256}
              autoFocus
              onChange={event => setTitle(event.target.value)}
              onPressEnter={() => {
                if (title.trim()) save();
              }}
            />
          ) : (
            <p>
              {t(
                'Delete "%s" and its conversation history? This cannot be undone. Saved charts and dashboards will remain.',
                item.title,
              )}
            </p>
          )}
        </Modal>
      )}
    </>
  );
}
