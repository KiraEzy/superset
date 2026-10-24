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
import copyTextToClipboard from 'src/utils/copy';
import UserMessage from './UserMessage';
jest.mock('src/utils/copy', () => jest.fn());
beforeEach(() => jest.clearAllMocks());

test('copy includes the full historical message', async () => {
  (copyTextToClipboard as jest.Mock).mockImplementation(async getText => {
    expect(await getText()).toBe('Original prompt');
  });
  render(<UserMessage content="Original prompt" onError={jest.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'Copy message' }));
  expect(await screen.findByRole('button', { name: 'Copied' })).toBeVisible();
});
test('edit is prefilled and cancellation does not resend or alter the message', () => {
  const onResend = jest.fn();
  render(
    <UserMessage
      content="Original prompt"
      onResend={onResend}
      onError={jest.fn()}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Edit message' }));
  const input = screen.getByRole('textbox', { name: 'Edit message' });
  expect(input).toHaveValue('Original prompt');
  fireEvent.change(input, { target: { value: 'Revised draft' } });
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.getByText('Original prompt')).toBeVisible();
  expect(onResend).not.toHaveBeenCalled();
});
test('resend sends the edited text and blocks empty input', async () => {
  const onResend = jest.fn().mockResolvedValue(undefined);
  render(
    <UserMessage content="Original" onResend={onResend} onError={jest.fn()} />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Edit message' }));
  const input = screen.getByRole('textbox', { name: 'Edit message' });
  fireEvent.change(input, { target: { value: ' ' } });
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  fireEvent.change(input, { target: { value: ' Revised question ' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  await waitFor(() =>
    expect(onResend).toHaveBeenCalledWith('Revised question'),
  );
  expect(onResend).toHaveBeenCalledTimes(1);
});
test('a failed resend keeps the edited draft for correction', async () => {
  const onResend = jest
    .fn()
    .mockRejectedValue(new Error('Stop the current turn first'));
  render(
    <UserMessage content="Original" onResend={onResend} onError={jest.fn()} />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Edit message' }));
  fireEvent.change(screen.getByRole('textbox', { name: 'Edit message' }), {
    target: { value: 'Revised' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  expect(await screen.findByText('Stop the current turn first')).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Edit message' })).toHaveValue(
    'Revised',
  );
});
