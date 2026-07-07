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

import { chromium } from '@playwright/test';
import { mkdir } from 'fs/promises';
import { dirname } from 'path';
import { AuthPage } from '../pages/AuthPage';
import { TIMEOUT } from '../utils/constants';
import {
  applyAiConnectionTestConfig,
  getAiConnectionTestConfigPath,
  loadAiConnectionTestConfig,
} from '../helpers/aiConnectionTestConfig';

async function main() {
  const config = loadAiConnectionTestConfig();
  if (!config) {
    console.error(
      `[seed-ai-connection] No config found at ${getAiConnectionTestConfigPath()}`,
    );
    console.error(
      '[seed-ai-connection] Copy config/ai-connection.test.example.json to config/ai-connection.test.local.json and fill in your credentials.',
    );
    process.exit(1);
  }

  const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:8088';
  const adminUsername = process.env.PLAYWRIGHT_ADMIN_USERNAME || 'admin';
  const adminPassword = process.env.PLAYWRIGHT_ADMIN_PASSWORD || 'general';

  console.log('[seed-ai-connection] Logging in and seeding AI connection config...');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ baseURL });
  const page = await context.newPage();

  try {
    const authPage = new AuthPage(page);
    await authPage.goto();
    await authPage.waitForLoginForm();
    await authPage.loginWithCredentials(adminUsername, adminPassword);
    await authPage.waitForLoginSuccess({ timeout: TIMEOUT.GLOBAL_SETUP });

    const applied = await applyAiConnectionTestConfig(page);
    if (!applied) {
      throw new Error('Failed to apply AI connection test config');
    }

    const authStatePath = 'playwright/.auth/user.json';
    await mkdir(dirname(authStatePath), { recursive: true });
    await context.storageState({ path: authStatePath });

    console.log(
      `[seed-ai-connection] Applied ${config.llmProvider} config and saved auth state to ${authStatePath}`,
    );
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch(error => {
  console.error('[seed-ai-connection] Failed:', error);
  process.exit(1);
});
