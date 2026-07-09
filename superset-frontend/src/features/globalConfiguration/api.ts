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
import type { GlobalConfigAdminPayload, GlobalConfigKnown } from './types';

export async function fetchPublicGlobalConfig(): Promise<GlobalConfigKnown> {
  const { json } = await SupersetClient.get({
    endpoint: '/api/v1/global_configuration/public/',
  });
  return json.result as GlobalConfigKnown;
}

export async function fetchGlobalConfigAdmin(): Promise<GlobalConfigAdminPayload> {
  const { json } = await SupersetClient.get({
    endpoint: '/api/v1/global_configuration/',
  });
  return json.result as GlobalConfigAdminPayload;
}

export async function saveGlobalConfig(body: Record<string, unknown>) {
  const { json } = await SupersetClient.put({
    endpoint: '/api/v1/global_configuration/',
    jsonPayload: body,
  });
  return json.result as GlobalConfigAdminPayload;
}

export async function deleteGlobalConfigKey(key: string) {
  const { json } = await SupersetClient.delete({
    endpoint: `/api/v1/global_configuration/${encodeURIComponent(key)}`,
  });
  return json.result as GlobalConfigAdminPayload;
}
