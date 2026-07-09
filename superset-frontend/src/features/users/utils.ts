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
import { t } from '@apache-superset/core/translation';
import { SupersetClient } from '@superset-ui/core';
import { SelectOption } from 'src/components/ListView';
import { setUserPosts } from 'src/features/posts/api';
import { FormValues } from './types';

// Under post-based RBAC, users are assigned to Posts (never roles directly).
// We create/update the user without roles/groups, then set their posts via the
// dedicated post assignment endpoint.
export const createUser = async (values: FormValues) => {
  const { confirmPassword, posts, roles, groups, ...payload } = values;
  if (payload.active == null) {
    payload.active = false;
  }
  const response = await SupersetClient.post({
    endpoint: '/api/v1/security/users/',
    // roles are intentionally empty: the backend assigns roles via posts only.
    jsonPayload: { ...payload, roles: [] },
  });
  const newUserId = response.json?.id;
  if (newUserId != null && Array.isArray(posts)) {
    await setUserPosts(Number(newUserId), posts as number[]);
  }
};

export const updateUser = async (user_Id: number, values: FormValues) => {
  const { confirmPassword, posts, roles, groups, ...payload } = values;
  await SupersetClient.put({
    endpoint: `/api/v1/security/users/${user_Id}`,
    jsonPayload: { ...payload },
  });
  if (Array.isArray(posts)) {
    await setUserPosts(user_Id, posts as number[]);
  }
};

export const deleteUser = async (userId: number) =>
  SupersetClient.delete({
    endpoint: `/api/v1/security/users/${userId}`,
  });

export const atLeastOneRoleOrGroup =
  (fieldToCheck: 'roles' | 'groups') =>
  ({
    getFieldValue,
  }: {
    getFieldValue: (field: string) => Array<SelectOption>;
  }) => ({
    validator(_: object, value: Array<SelectOption>) {
      const current = value || [];
      const other = getFieldValue(fieldToCheck) || [];
      if (current.length === 0 && other.length === 0) {
        return Promise.reject(
          new Error(t('Please select at least one role or group')),
        );
      }
      return Promise.resolve();
    },
  });

export const atLeastOnePost = () => ({
  validator(_: object, value: Array<number> | undefined) {
    if (!value || value.length === 0) {
      return Promise.reject(new Error(t('Please assign at least one post')));
    }
    return Promise.resolve();
  },
});
