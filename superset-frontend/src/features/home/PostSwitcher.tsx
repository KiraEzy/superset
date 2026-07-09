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
import { Button, Dropdown, Icons } from '@superset-ui/core/components';
import { useToasts } from 'src/components/MessageToasts/withToasts';
import { setActivePost } from 'src/features/posts/api';
import type { UserPost } from 'src/types/bootstrapTypes';

export interface PostSwitcherProps {
  activePost?: UserPost | null;
  availablePosts?: UserPost[];
}

export default function PostSwitcher({
  activePost,
  availablePosts = [],
}: PostSwitcherProps) {
  const theme = useTheme();
  const { addDangerToast } = useToasts();
  const [switching, setSwitching] = useState(false);

  // Nothing to switch between: hide the control entirely.
  if (!availablePosts || availablePosts.length <= 1) {
    return null;
  }

  const handleSelect = async (postId: number) => {
    if (activePost && postId === activePost.id) {
      return;
    }
    setSwitching(true);
    try {
      await setActivePost(postId);
      // Full reload so post-scoped permissions and the menu are rebuilt.
      window.location.reload();
    } catch (error) {
      addDangerToast(t('Could not switch post. Please try again.'));
      setSwitching(false);
    }
  };

  const label = activePost?.label || activePost?.name || t('Choose post');

  return (
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
          display: flex;
          align-items: center;
          gap: ${theme.sizeUnit}px;
        `}
        data-test="post-switcher"
      >
        <Icons.UserOutlined iconSize="m" />
        {label}
        <Icons.DownOutlined iconSize="s" />
      </Button>
    </Dropdown>
  );
}
