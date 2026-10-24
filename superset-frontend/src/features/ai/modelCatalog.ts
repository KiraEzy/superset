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

import { SupersetClient, getClientErrorObject } from '@superset-ui/core';
import { AiConnectionConfig } from './aiConnectionConfig';

export interface PublicModel {
  id: string;
  name: string;
  connection: string;
  vision: boolean;
  default: boolean;
}
export interface CatalogModel extends PublicModel {
  connection_id: string;
  status: string;
  ready: boolean;
  published: boolean;
  position: number | null;
}
export interface ModelConnection {
  id: string;
  label: string;
  revision: number;
  config: Pick<
    AiConnectionConfig,
    | 'llmProvider'
    | 'llmApiBaseUrl'
    | 'llmApiKey'
    | 'llmModel'
    | 'llmAdapter'
    | 'showModelReasoning'
  >;
}
export interface ModelCatalogue {
  connections: ModelConnection[];
  models: CatalogModel[];
}
export async function catalogRequest<T>(path = '', body?: object): Promise<T> {
  try {
    const endpoint = `/api/v1/ai_connection/models/${path}`;
    const { json } =
      body === undefined
        ? await SupersetClient.get({ endpoint })
        : await SupersetClient.post({ endpoint, jsonPayload: body });
    return json.result as T;
  } catch (error) {
    const parsed = await getClientErrorObject(
      error as Parameters<typeof getClientErrorObject>[0],
    );
    throw new Error(
      parsed.message || parsed.error || 'Connection request failed',
    );
  }
}
export async function waitVerification(
  id: string,
  onProgress: (message: string) => void,
): Promise<string> {
  const deadline = Date.now() + 360000;
  while (Date.now() < deadline) {
    const job = await catalogRequest<{
      status: string;
      message: string;
      connection_id: string;
    }>(`jobs/${id}`);
    onProgress(job.message);
    if (job.status === 'completed') return job.connection_id;
    if (job.status === 'failed') throw new Error(job.message);
    await new Promise(resolve => setTimeout(resolve, 1500));
  }
  throw new Error(
    'Verification is taking longer than expected. Reload to check its result.',
  );
}
