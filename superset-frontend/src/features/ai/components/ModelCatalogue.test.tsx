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
  within,
} from 'spec/helpers/testing-library';
import ModelCatalogue from './ModelCatalogue';
import * as api from '../modelCatalog';
const data: api.ModelCatalogue = {
  connections: [],
  models: [
    {
      id: 'one',
      name: 'One',
      connection: 'Local',
      connection_id: 'local',
      vision: false,
      default: true,
      status: 'verified',
      ready: true,
      published: true,
      position: 0,
    },
    {
      id: 'two',
      name: 'Two',
      connection: 'Hosted',
      connection_id: 'hosted',
      vision: true,
      default: false,
      status: 'discovered',
      ready: false,
      published: false,
      position: null,
    },
  ],
};
afterEach(() => jest.restoreAllMocks());
test('moving an unverified model queues verification before adding it', async () => {
  const request = jest
    .spyOn(api, 'catalogRequest')
    .mockResolvedValue({ id: 'job' });
  const verify = jest
    .spyOn(api, 'waitVerification')
    .mockResolvedValue('hosted');
  const reload = jest.fn().mockResolvedValue(undefined);
  render(<ModelCatalogue data={data} reload={reload} />);
  fireEvent.click(screen.getByRole('checkbox', { name: /Two/ }));
  fireEvent.click(
    screen.getByRole('button', { name: 'Verify and add selected models' }),
  );
  await waitFor(() => expect(reload).toHaveBeenCalled());
  expect(request).toHaveBeenCalledWith('two/verify', {});
  expect(verify).toHaveBeenCalledWith('job', expect.any(Function));
  expect(
    screen.getByRole('group', { name: 'Available in Chat' }),
  ).toHaveTextContent('Two');
});
test('failed verification leaves the model in the discovered list', async () => {
  jest.spyOn(api, 'catalogRequest').mockResolvedValue({ id: 'job' });
  jest
    .spyOn(api, 'waitVerification')
    .mockRejectedValue(new Error('Unsupported tools'));
  render(<ModelCatalogue data={data} reload={jest.fn()} />);
  fireEvent.click(screen.getByRole('checkbox', { name: /Two/ }));
  fireEvent.click(
    screen.getByRole('button', { name: 'Verify and add selected models' }),
  );
  expect(await screen.findByText('Unsupported tools')).toBeVisible();
  expect(
    screen.getByRole('group', { name: 'Available in Chat' }),
  ).not.toHaveTextContent('Two');
});

test('model settings opens without changing the publication selection', async () => {
  const values = {
    context_window_tokens: 32768,
    response_tokens: 4096,
    tool_result_tokens: 4096,
  };
  render(
    <ModelCatalogue
      data={{
        ...data,
        models: [
          {
            ...data.models[0],
            runtime_settings: {
              values,
              defaults: values,
              revision: 0,
              input_allowance_tokens: 24576,
            },
          },
        ],
      }}
      reload={jest.fn()}
    />,
  );
  fireEvent.click(
    screen.getByRole('button', { name: 'Settings for One / Local' }),
  );
  const dialog = await screen.findByRole('dialog', { name: 'Model settings' });
  expect(
    within(dialog).getByRole('spinbutton', { name: 'Context window (tokens)' }),
  ).toHaveValue('32768');
  expect(
    screen.getByRole('checkbox', { name: 'One / Local' }),
  ).not.toBeChecked();
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
  expect(
    screen.getByRole('checkbox', { name: 'One / Local' }),
  ).not.toBeChecked();
});
