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

import { render, screen } from 'spec/helpers/testing-library';
import { runtimeGet } from 'src/features/ai/runtime';
import AI from './index';

jest.mock('src/features/ai/runtime', () => ({ runtimeGet: jest.fn() }));
jest.mock('src/features/ai/components/RuntimeWorkspace', () => () => (
  <div>SDK workspace</div>
));

test('enabled Chat opens only the SDK workspace', async () => {
  (runtimeGet as jest.Mock).mockResolvedValue({ enabled: true });
  render(<AI />);
  expect(await screen.findByText('SDK workspace')).toBeInTheDocument();
});

test('disabled Chat shows an unavailable state without the legacy composer', async () => {
  (runtimeGet as jest.Mock).mockResolvedValue({ enabled: false });
  render(<AI />);
  expect(
    await screen.findByText('AI Chat is temporarily unavailable.'),
  ).toBeInTheDocument();
  expect(screen.queryByText('SDK workspace')).not.toBeInTheDocument();
});
