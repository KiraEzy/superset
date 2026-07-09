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
import { css, styled } from '@apache-superset/core/theme';
import { Button } from '@superset-ui/core/components';
import getBootstrapData from 'src/utils/getBootstrapData';
import { useToasts } from 'src/components/MessageToasts/withToasts';
import { setActivePost } from 'src/features/posts/api';
import type { UserPost } from 'src/types/bootstrapTypes';

const Container = styled.div`
  ${({ theme }) => css`
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 70vh;
    gap: ${theme.sizeUnit * 4}px;
    padding: ${theme.sizeUnit * 6}px;
  `}
`;

const Header = styled.div`
  ${({ theme }) => css`
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: ${theme.sizeUnit}px;
    text-align: center;
    max-width: 560px;
  `}
`;

const PostList = styled.ul`
  ${({ theme }) => css`
    list-style: none;
    margin: 0;
    padding: 0;
    width: 100%;
    max-width: 560px;
    border: 1px solid ${theme.colorBorder};
    border-radius: ${theme.borderRadius}px;
    overflow: hidden;
    background: ${theme.colorBgContainer};
  `}
`;

const PostRow = styled.li`
  ${({ theme }) => css`
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: ${theme.sizeUnit * 3}px;
    padding: ${theme.sizeUnit * 3}px ${theme.sizeUnit * 4}px;
    border-bottom: 1px solid ${theme.colorBorderSecondary};

    &:last-child {
      border-bottom: none;
    }
  `}
`;

const PostName = styled.span`
  ${({ theme }) => css`
    font-size: ${theme.fontSizeLG}px;
    font-weight: ${theme.fontWeightStrong};
    color: ${theme.colorText};
  `}
`;

const RETURN_URL = '/superset/welcome/';

function ChoosePost() {
  const { addDangerToast } = useToasts();
  const user = getBootstrapData()?.user as
    | { availablePosts?: UserPost[]; firstName?: string }
    | undefined;
  const posts = user?.availablePosts || [];
  const [submitting, setSubmitting] = useState<number | null>(null);

  const handleSelect = async (post: UserPost) => {
    setSubmitting(post.id);
    try {
      await setActivePost(post.id);
      // Full reload so post-scoped permissions and menu are rebuilt.
      window.location.href = RETURN_URL;
    } catch (error) {
      addDangerToast(
        t('Could not log in as %s. Please try again.', post.label || post.name),
      );
      setSubmitting(null);
    }
  };

  if (posts.length === 0) {
    return (
      <Container>
        <h2>{t('No posts assigned')}</h2>
        <p>
          {t(
            'Your account has no posts assigned yet. Please contact an administrator to be assigned a post before you can access the application.',
          )}
        </p>
      </Container>
    );
  }

  return (
    <Container>
      <Header>
        <h2>{t('Choose a post to log in as')}</h2>
        <p>
          {t(
            'Your permissions for this session come from the post you select.',
          )}
        </p>
      </Header>
      <PostList>
        {posts.map(post => (
          <PostRow key={post.id} data-test={`choose-post-${post.id}`}>
            <PostName>{post.label || post.name}</PostName>
            <Button
              buttonStyle="primary"
              loading={submitting === post.id}
              disabled={submitting !== null && submitting !== post.id}
              onClick={() => handleSelect(post)}
            >
              {t('Login')}
            </Button>
          </PostRow>
        ))}
      </PostList>
    </Container>
  );
}

export default ChoosePost;
