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
  render,
  screen,
  selectOption,
  waitFor,
} from 'spec/helpers/testing-library';
import * as config from '../aiConnectionConfig';
import McpToolAccessEditor from './McpToolAccessEditor';

afterEach(() => jest.restoreAllMocks());

test('admin editing preserves existing role restrictions and new user rules grant no tools by default', async () => {
  jest
    .spyOn(config, 'fetchMcpAccessOptions')
    .mockResolvedValue({
      roles: ['Alpha'],
      users: ['alice'],
      tools: ['health_check', 'list_datasets'],
    });
  const onChange = jest.fn();
  render(
    <McpToolAccessEditor
      value={{ roles: { Alpha: ['health_check'] }, users: {} }}
      onChange={onChange}
    />,
  );
  await waitFor(() =>
    expect(
      screen.getByRole('combobox', { name: 'Restricted users' }),
    ).toBeEnabled(),
  );
  expect(screen.getByText('health_check')).toBeVisible();
  await selectOption('alice', 'Restricted users');
  expect(onChange).toHaveBeenCalledWith({
    roles: { Alpha: ['health_check'] },
    users: { alice: [] },
  });
});

test('failed option loading never clears the saved restrictions', async () => {
  jest
    .spyOn(config, 'fetchMcpAccessOptions')
    .mockRejectedValue(new Error('unavailable'));
  const onChange = jest.fn();
  render(
    <McpToolAccessEditor
      value={{ roles: { Alpha: [] }, users: {} }}
      onChange={onChange}
    />,
  );
  expect(
    await screen.findByText(/Tool access options could not load/),
  ).toBeVisible();
  expect(onChange).not.toHaveBeenCalled();
});
