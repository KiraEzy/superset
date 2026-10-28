/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership. The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License. You may obtain a copy of the License at
 * http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from 'spec/helpers/testing-library';
import ModelSettingsModal from './ModelSettingsModal';
import * as api from '../modelCatalog';

const model: api.CatalogModel = {
  id: 'qwen',
  name: 'Qwen',
  connection: 'Custom',
  connection_id: 'custom',
  vision: false,
  default: true,
  status: 'verified',
  ready: true,
  published: true,
  position: 0,
  runtime_settings: {
    revision: 3,
    input_allowance_tokens: 57344,
    values: {
      context_window_tokens: 65536,
      response_tokens: 4096,
      tool_result_tokens: 4096,
    },
    defaults: {
      context_window_tokens: 32768,
      response_tokens: 4096,
      tool_result_tokens: 4096,
    },
  },
};
afterEach(() => jest.restoreAllMocks());

test('saves edited values against the selected model and revision', async () => {
  const request = jest
    .spyOn(api, 'catalogRequest')
    .mockResolvedValue({ saved: true });
  const onSaved = jest.fn().mockResolvedValue(undefined);
  const onHide = jest.fn();
  render(
    <ModelSettingsModal model={model} onSaved={onSaved} onHide={onHide} />,
  );
  fireEvent.change(
    screen.getByRole('spinbutton', { name: 'Maximum response tokens' }),
    { target: { value: '8192' } },
  );
  fireEvent.click(screen.getByRole('button', { name: 'Save model settings' }));
  await waitFor(() => expect(onHide).toHaveBeenCalled());
  expect(request).toHaveBeenCalledWith('qwen/settings', {
    revision: 3,
    values: {
      context_window_tokens: 65536,
      response_tokens: 8192,
      tool_result_tokens: 4096,
    },
  });
  expect(onSaved).toHaveBeenCalled();
});

test('invalid reservations prevent saving and cancellation makes no request', () => {
  const request = jest.spyOn(api, 'catalogRequest');
  const onHide = jest.fn();
  render(
    <ModelSettingsModal model={model} onSaved={jest.fn()} onHide={onHide} />,
  );
  fireEvent.change(
    screen.getByRole('spinbutton', { name: 'Context window (tokens)' }),
    { target: { value: '4096' } },
  );
  expect(
    screen.getByRole('button', { name: 'Save model settings' }),
  ).toBeDisabled();
  expect(screen.getByText(/Leave at least 1,024/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(onHide).toHaveBeenCalled();
  expect(request).not.toHaveBeenCalled();
});

test('restore defaults is only persisted when Save is clicked', async () => {
  const request = jest
    .spyOn(api, 'catalogRequest')
    .mockResolvedValue({ saved: true });
  const onHide = jest.fn();
  render(
    <ModelSettingsModal
      model={model}
      onSaved={jest.fn().mockResolvedValue(undefined)}
      onHide={onHide}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Restore defaults' }));
  expect(
    screen.getByRole('spinbutton', { name: 'Context window (tokens)' }),
  ).toHaveValue('32768');
  expect(request).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Save model settings' }));
  await waitFor(() => expect(onHide).toHaveBeenCalled());
  expect(request).toHaveBeenCalledWith('qwen/settings', {
    revision: 3,
    reset: true,
  });
});

test('a conflicting edit stays visible and preserves the local draft', async () => {
  jest
    .spyOn(api, 'catalogRequest')
    .mockRejectedValue(
      new Error('Model settings changed. Reload the page before saving.'),
    );
  const onHide = jest.fn();
  render(
    <ModelSettingsModal model={model} onSaved={jest.fn()} onHide={onHide} />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Save model settings' }));
  expect(await screen.findByText(/Model settings changed/)).toBeInTheDocument();
  expect(onHide).not.toHaveBeenCalled();
});
