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
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from 'spec/helpers/testing-library';
import ContextUsageRing from './ContextUsageRing';

test('ring exposes current request usage on hover and focus', async () => {
  render(
    <ContextUsageRing
      usage={{
        model: 'test',
        context_window_tokens: 256000,
        input_tokens: 40000,
        output_tokens: 2500,
        output_limit_tokens: 64000,
        input_allowance_tokens: 187904,
        tool_result_reserve_tokens: 4096,
        estimated: false,
      }}
    />,
  );
  const ring = screen.getByRole('button', { name: '17% context used' });
  fireEvent.focus(ring);
  await waitFor(() =>
    expect(screen.getByText('42,500 / 256,000 tokens')).toBeVisible(),
  );
  expect(
    screen.getByText('Provider-reported usage for the latest model request.'),
  ).toBeVisible();
  expect(screen.getByText('Output limit')).toBeVisible();
});

test('unknown context is not presented as zero usage', async () => {
  render(<ContextUsageRing />);
  fireEvent.mouseEnter(
    screen.getByRole('button', { name: 'Context usage unavailable' }),
  );
  await waitFor(() =>
    expect(
      screen.getByText('Usage appears when a model request starts.'),
    ).toBeVisible(),
  );
});
