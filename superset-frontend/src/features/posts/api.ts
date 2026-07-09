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
import { SupersetClient } from '@superset-ui/core';
import { FormValues, PostObject } from './types';

const toPayload = (values: FormValues) => ({
  name: values.name,
  label: values.label,
  description: values.description,
  active: values.active ?? true,
  role_ids: values.roles || [],
  user_ids: (values.users || []).map(user => user.value),
});

export const fetchPosts = async (): Promise<PostObject[]> => {
  const response = await SupersetClient.get({ endpoint: '/api/v1/post/' });
  return (response.json?.result as PostObject[]) || [];
};

export const createPost = async (values: FormValues) => {
  await SupersetClient.post({
    endpoint: '/api/v1/post/',
    jsonPayload: toPayload(values),
  });
};

export const updatePost = async (postId: number, values: FormValues) => {
  await SupersetClient.put({
    endpoint: `/api/v1/post/${postId}`,
    jsonPayload: toPayload(values),
  });
};

export const deletePost = async (postId: number) =>
  SupersetClient.delete({ endpoint: `/api/v1/post/${postId}` });

export const setUserPosts = async (userId: number, postIds: number[]) =>
  SupersetClient.put({
    endpoint: `/api/v1/post/user/${userId}`,
    jsonPayload: { post_ids: postIds },
  });

export type ActivePostResponse = {
  active_post: { id: number; name: string; label?: string } | null;
  available_posts: { id: number; name: string; label?: string }[];
};

export const fetchActivePost = async (): Promise<ActivePostResponse> => {
  const response = await SupersetClient.get({
    endpoint: '/api/v1/active_post/',
  });
  return response.json?.result as ActivePostResponse;
};

export const setActivePost = async (postId: number) =>
  SupersetClient.post({
    endpoint: '/api/v1/active_post/',
    jsonPayload: { post_id: postId },
  });
