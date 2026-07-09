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
import { useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { css, useTheme } from '@apache-superset/core/theme';
import { Button, Dropdown, Icons, Tooltip } from '@superset-ui/core/components';
import { useToasts } from 'src/components/MessageToasts/withToasts';
import { usePublicGlobalConfig } from 'src/features/globalConfiguration/usePublicGlobalConfig';
import { setActivePost } from 'src/features/posts/api';
import type { UserPost } from 'src/types/bootstrapTypes';

export interface PostSwitcherProps {
  firstName?: string;
  lastName?: string;
  username?: string;
  activePost?: UserPost | null;
  availablePosts?: UserPost[];
}

export function getPostSwitcherDisplayName({
  firstName,
  lastName,
  username,
}: Pick<PostSwitcherProps, 'firstName' | 'lastName' | 'username'>): string {
  const parts = [firstName, lastName]
    .map(part => (part || '').trim())
    .filter(Boolean);
  if (parts.length > 0) {
    return parts.join(' ');
  }
  return (username || '').trim();
}

export default function PostSwitcher({
  firstName,
  lastName,
  username,
  activePost,
  availablePosts = [],
}: PostSwitcherProps) {
  const theme = useTheme();
  const { addDangerToast } = useToasts();
  const { displayNameMaxWidthPx } = usePublicGlobalConfig();
  const [switching, setSwitching] = useState(false);

  const displayName = getPostSwitcherDisplayName({
    firstName,
    lastName,
    username,
  });
  // Single i18n string; split on a sentinel so only the name segment truncates.
  const namePlaceholder = '\u0000';
  const greetingTemplate = t('Hi, %s, you are logged in as,', namePlaceholder);
  const [greetingBefore = '', greetingAfter = ''] =
    greetingTemplate.split(namePlaceholder);
  const label = activePost?.label || activePost?.name || t('Choose post');
  const canSwitch = availablePosts.length > 1;

  const handleSelect = async (postId: number) => {
    if (activePost && postId === activePost.id) {
      return;
    }
    setSwitching(true);
    try {
      await setActivePost(postId);
      window.location.reload();
    } catch (error) {
      addDangerToast(t('Could not switch post. Please try again.'));
      setSwitching(false);
    }
  };

  const displayNameEllipsisCss = css`
    display: inline-block;
    max-width: ${displayNameMaxWidthPx}px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    vertical-align: baseline;
  `;

  const rowCss = css`
    display: flex;
    align-items: baseline;
    gap: ${theme.sizeUnit}px;
    color: ${theme.colorPrimary};
  `;

  const greetingCss = css`
    display: inline-flex;
    align-items: baseline;
  `;

  const postLabelNode = (
    <span data-test="post-switcher-label">{label}</span>
  );

  return (
    <div css={rowCss} data-test="post-switcher-root">
      <Icons.UserOutlined iconSize="m" />
      <span css={greetingCss} data-test="post-switcher-greeting">
        {greetingBefore}
        <Tooltip title={displayName || undefined}>
          <span
            css={displayNameEllipsisCss}
            title={displayName}
            data-test="post-switcher-display-name"
            data-max-width={String(displayNameMaxWidthPx)}
          >
            {displayName}
          </span>
        </Tooltip>
        {greetingAfter}
      </span>
      {canSwitch ? (
        <Dropdown
          menu={{
            selectable: true,
            selectedKeys: activePost ? [String(activePost.id)] : [],
            items: availablePosts.map(post => ({
              key: String(post.id),
              label: post.label || post.name,
              onClick: () => handleSelect(post.id),
            })),
          }}
        >
          <Button
            buttonStyle="link"
            loading={switching}
            css={css`
              display: inline-flex;
              align-items: baseline;
              gap: ${theme.sizeUnit}px;
              padding: 0;
              line-height: inherit;
              height: auto;
              min-height: 0;
            `}
            data-test="post-switcher"
          >
            {postLabelNode}
            <Icons.DownOutlined iconSize="s" />
          </Button>
        </Dropdown>
      ) : (
        postLabelNode
      )}
    </div>
  );
}
