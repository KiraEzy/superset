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
import { Button } from '@superset-ui/core/components';
import { Icons } from '@superset-ui/core/components/Icons';
import copyTextToClipboard from 'src/utils/copy';

const Bar = styled.div`
  display: flex;
  align-items: center;
  gap: 2px;
  margin: 2px 0 0 -6px;
  padding: 0;
`;
const ActionButton = styled(Button)`
  &&& {
    width: 28px;
    min-width: 28px;
    height: 28px;
    padding: 0;
    border: 0;
    box-shadow: none;
    background: transparent;
    margin: 0;
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

export default function ReplyActions({
  content,
  disabled,
  onRetry,
  onFork,
  onError,
}: {
  content: string;
  disabled?: boolean;
  onRetry?: () => void;
  onFork?: () => void;
  onError: (reason: unknown) => void;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <Bar role="group" aria-label={t('Reply actions')}>
      <ActionButton
        buttonStyle="tertiary"
        title={copied ? t('Copied') : t('Copy reply')}
        aria-label={copied ? t('Copied') : t('Copy reply')}
        disabled={!content}
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
      </ActionButton>
      <ActionButton
        buttonStyle="tertiary"
        title={t('Retry in a new branch')}
        aria-label={t('Retry reply')}
        disabled={disabled || !onRetry}
        onClick={onRetry}
      >
        <Icons.ReloadOutlined aria-hidden />
      </ActionButton>
      <ActionButton
        buttonStyle="tertiary"
        title={t('Fork chat from this reply')}
        aria-label={t('Fork chat')}
        disabled={disabled || !onFork}
        onClick={onFork}
      >
        <Icons.ShareAltOutlined aria-hidden />
      </ActionButton>
    </Bar>
  );
}
