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

import { useRef, useState } from 'react';
import { SupersetClient, getClientErrorObject } from '@superset-ui/core';
import { styled } from '@apache-superset/core/theme';
import { t } from '@apache-superset/core/translation';
import { Button, Dropdown, Input } from '@superset-ui/core/components';
import { Icons } from '@superset-ui/core/components/Icons';
import { PublicModel } from '../modelCatalog';
import { ImageReference } from '../runtime';

export interface ImageDraft {
  key: string;
  file: File;
  preview: string;
  image?: ImageReference;
  error?: string;
}
const Shell = styled.div`
  width: 100%;
  max-width: 768px;
  margin: 8px auto 0;
  padding: 8px;
  border: 1px solid ${({ theme }) => theme.colorBorder};
  border-radius: 28px;
  background: ${({ theme }) => theme.colorBgContainer};
  box-shadow: 0 2px 8px ${({ theme }) => theme.colorFillTertiary};
  .input-line {
    display: flex;
    align-items: flex-end;
    gap: 4px;
    min-width: 0;
  }
  .message-input {
    flex: 1;
    min-width: 0;
  }
  textarea.ant-input {
    padding: 8px;
    border: 0;
    box-shadow: none;
    background: transparent;
    resize: none;
  }
  .model-select {
    display: flex;
    align-items: center;
    gap: 6px;
    width: auto;
    min-width: 0;
    max-width: min(180px, 34%);
    cursor: pointer;
    user-select: none;
    caret-color: transparent;
    height: 36px;
    padding: 0 10px;
    border: 0;
    border-radius: 18px;
    background: transparent;
    color: ${({ theme }) => theme.colorTextSecondary};
    box-shadow: none;
    font-weight: normal;
  }
  .model-select .model-name {
    display: block;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .model-select svg {
    flex-shrink: 0;
    width: 12px;
    height: 12px;
  }
  .composer-icon {
    width: 36px;
    min-width: 36px;
    height: 36px;
    padding: 0;
    border-radius: 50%;
  }
  .image-drafts {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    padding: 4px 8px 8px;
  }
  .image-draft {
    position: relative;
    width: 88px;
  }
  .image-draft img {
    width: 80px;
    height: 64px;
    object-fit: cover;
    border-radius: 8px;
  }
  .image-draft .remove {
    position: absolute;
    top: -4px;
    right: 0;
    width: 24px;
    min-width: 24px;
    height: 24px;
    padding: 0;
    border-radius: 50%;
  }
  .image-draft small {
    display: block;
    font-size: 11px;
    overflow-wrap: anywhere;
  }
  .composer-warning {
    margin: 4px 8px;
    color: ${({ theme }) => theme.colorTextSecondary};
  }
  @media (max-width: 600px) {
    .input-line {
      flex-wrap: wrap;
    }
    .message-input {
      flex-basis: calc(100% - 44px);
    }
    .model-select {
      margin-left: 40px;
      width: calc(100% - 130px);
      max-width: none;
      flex: 1;
    }
  }
`;
const ModelMenu = styled.div`
  .ant-dropdown-menu {
    min-width: 240px;
    max-width: min(420px, calc(100vw - 32px));
    max-height: min(360px, 50vh);
    overflow-y: auto;
    padding: 6px;
    border: 1px solid ${({ theme }) => theme.colorBorder};
    border-radius: 18px;
    background: ${({ theme }) => theme.colorBgContainer};
    box-shadow: 0 4px 12px ${({ theme }) => theme.colorFillSecondary};
  }
  .ant-dropdown-menu-item {
    padding: 10px 12px;
    border-radius: 10px;
    font-weight: normal;
  }
  .model-option {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }
  .model-option-name {
    overflow-wrap: anywhere;
  }
  .model-option svg {
    flex-shrink: 0;
  }
`;
export default function ChatComposer({
  value,
  onChange,
  models,
  modelId,
  onModelChange,
  images,
  onImagesChange,
  imageLimits,
  retainedImageCount,
  busy,
  running,
  onSend,
  onStop,
  onError,
}: {
  value: string;
  onChange: (value: string) => void;
  models: PublicModel[];
  modelId: string;
  onModelChange: (id: string) => void;
  images: ImageDraft[];
  onImagesChange: (
    images: ImageDraft[] | ((prior: ImageDraft[]) => ImageDraft[]),
  ) => void;
  imageLimits: { count: number; bytes: number };
  retainedImageCount: number;
  busy: boolean;
  running: boolean;
  onSend: () => void;
  onStop: () => void;
  onError: (error: unknown) => void;
}) {
  const picker = useRef<HTMLInputElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const imageReady = models.find(m => m.id === modelId)?.vision ?? false;
  const selected = models.some(m => m.id === modelId);
  const upload = async (draft: ImageDraft) => {
    const data = new FormData();
    data.append('file', draft.file);
    try {
      const { json } = await SupersetClient.post({
        endpoint: '/api/v1/ai/images/',
        postPayload: data,
      });
      onImagesChange(prior =>
        prior.map(item =>
          item.key === draft.key
            ? {
                ...item,
                image: json.result as ImageReference,
                error: undefined,
              }
            : item,
        ),
      );
    } catch (error) {
      const parsed = await getClientErrorObject(
        error as Parameters<typeof getClientErrorObject>[0],
      );
      onImagesChange(prior =>
        prior.map(item =>
          item.key === draft.key
            ? { ...item, error: parsed.message || t('Upload failed') }
            : item,
        ),
      );
    }
  };
  const addFiles = (files: File[]) => {
    if (running || busy) return;
    if (!imageReady) {
      onError(
        new Error(t('Choose an image-verified model before attaching images.')),
      );
      return;
    }
    if (files.length + images.length + retainedImageCount > imageLimits.count) {
      onError(
        new Error(
          t('Conversation image limit reached. Start a focused new chat.'),
        ),
      );
      return;
    }
    if (
      files.some(
        file =>
          !['image/png', 'image/jpeg', 'image/webp'].includes(file.type) ||
          file.size > imageLimits.bytes,
      )
    ) {
      onError(
        new Error(
          t(
            'Use JPEG, PNG or static WebP images within the upload size limit.',
          ),
        ),
      );
      return;
    }
    const drafts = files.map(file => ({
      key: `${Date.now()}-${Math.random()}`,
      file,
      preview: URL.createObjectURL(file),
    }));
    onImagesChange(prior => [...prior, ...drafts]);
    drafts.forEach(upload);
  };
  const remove = async (item: ImageDraft) => {
    if (item.image) {
      try {
        await SupersetClient.delete({
          endpoint: `/api/v1/ai/images/${item.image.id}`,
        });
      } catch (error) {
        onError(error);
        return;
      }
    }
    URL.revokeObjectURL(item.preview);
    onImagesChange(prior => prior.filter(draft => draft.key !== item.key));
  };
  const canSend =
    !busy &&
    selected &&
    Boolean(value.trim() || images.length) &&
    images.every(i => i.image && !i.error);
  const selectedModel = models.find(m => m.id === modelId);
  const modelItems = models.map(model => ({
    key: model.id,
    label: (
      <span className="model-option" title={model.connection}>
        <span className="model-option-name">{model.name}</span>
        {model.id === modelId && <Icons.CheckOutlined aria-hidden />}
      </span>
    ),
    disabled: (retainedImageCount > 0 || images.length > 0) && !model.vision,
  }));
  return (
    <Shell
      onDragOver={e => {
        if (e.dataTransfer.types.includes('Files')) e.preventDefault();
      }}
      onDrop={e => {
        e.preventDefault();
        addFiles(Array.from(e.dataTransfer.files));
      }}
      onPaste={e => {
        const files = Array.from(e.clipboardData.files);
        if (files.length) {
          e.preventDefault();
          addFiles(files);
        }
      }}
    >
      <input
        ref={picker}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        hidden
        aria-label={t('Choose images')}
        onChange={e => {
          addFiles(Array.from(e.target.files ?? []));
          e.target.value = '';
        }}
      />
      {images.length > 0 && (
        <div className="image-drafts" aria-label={t('Attached images')}>
          {images.map(item => (
            <div className="image-draft" key={item.key}>
              <img src={item.preview} alt={item.file.name} />
              {(item.image || item.error) && (
                <Button
                  className="remove"
                  disabled={busy}
                  aria-label={t('Remove image %s', item.file.name)}
                  onClick={() => remove(item)}
                >
                  <Icons.CloseOutlined />
                </Button>
              )}
              {!item.image && !item.error && (
                <small role="status">{t('Uploading...')}</small>
              )}
              {item.error && (
                <>
                  <small role="alert">{item.error}</small>
                  <Button
                    onClick={() => {
                      onImagesChange(prior =>
                        prior.map(i =>
                          i.key === item.key ? { ...i, error: undefined } : i,
                        ),
                      );
                      upload(item);
                    }}
                  >
                    {t('Retry upload')}
                  </Button>
                </>
              )}
            </div>
          ))}
        </div>
      )}
      {!selected && (
        <p className="composer-warning" role="status">
          {t('Choose an available model to continue.')}
        </p>
      )}
      <div className="input-line">
        <Dropdown
          open={menuOpen}
          onOpenChange={setMenuOpen}
          trigger={['click']}
          placement="topLeft"
          menu={{
            items: [
              {
                key: 'image',
                label: t('Attach images'),
                icon: <Icons.FileImageOutlined />,
                disabled: running || busy || !imageReady,
              },
            ],
            onClick: () => {
              setMenuOpen(false);
              picker.current?.click();
            },
          }}
        >
          <Button
            className="composer-icon"
            buttonStyle="tertiary"
            aria-label={t('Add attachment')}
            title={
              imageReady
                ? t('Add attachment')
                : t('Choose an image-verified model to attach images')
            }
            disabled={running || busy}
          >
            <Icons.PlusOutlined />
          </Button>
        </Dropdown>
        <div className="message-input">
          <Input.TextArea
            aria-label={t('Message')}
            value={value}
            maxLength={64000}
            onChange={e => onChange(e.target.value)}
            placeholder={
              running
                ? t('Add guidance while work continues?')
                : t('Ask about your data')
            }
            autoSize={{ minRows: 1, maxRows: 8 }}
            onKeyDown={e => {
              if (
                e.key === 'Enter' &&
                !e.shiftKey &&
                !e.nativeEvent.isComposing
              ) {
                e.preventDefault();
                if (canSend) onSend();
              }
            }}
          />
        </div>
        <Dropdown
          trigger={['click']}
          placement="topRight"
          disabled={running || busy || !models.length}
          dropdownRender={menu => <ModelMenu>{menu}</ModelMenu>}
          menu={{
            items: modelItems,
            selectable: true,
            selectedKeys: selectedModel ? [modelId] : [],
            onClick: ({ key }) => onModelChange(key),
          }}
        >
          <Button
            className="model-select"
            buttonStyle="tertiary"
            aria-label={t('Chat model')}
            title={selectedModel?.name || t('Choose model')}
            disabled={running || busy || !models.length}
          >
            <span className="model-name">
              {selectedModel?.name || t('Choose model')}
            </span>
            <Icons.DownOutlined aria-hidden />
          </Button>
        </Dropdown>
        {running && (
          <Button
            className="composer-icon"
            aria-label={t('Stop')}
            title={t('Stop')}
            onClick={onStop}
          >
            <Icons.StopOutlined />
          </Button>
        )}
        <Button
          className="composer-icon"
          type="primary"
          aria-label={running ? t('Send guidance') : t('Send')}
          title={running ? t('Send guidance') : t('Send')}
          disabled={!canSend}
          onClick={onSend}
        >
          <Icons.UpOutlined />
        </Button>
      </div>
    </Shell>
  );
}
