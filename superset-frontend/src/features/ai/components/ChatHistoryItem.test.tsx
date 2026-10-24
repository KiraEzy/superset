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
import * as api from '../aiChatSessionApi';
import ChatHistoryItem from './ChatHistoryItem';

jest.mock('../aiChatSessionApi', () => ({
  updateChatSessionPin: jest.fn(),
  updateChatSessionTitle: jest.fn(),
  deleteChatSession: jest.fn(),
}));
const item = {
  id: 'thread-1',
  dbId: 1,
  title: 'Original',
  createdAt: 1,
  updatedAt: 2,
};
const onUpdated = jest.fn();
const onDeleted = jest.fn();
const onError = jest.fn();
const onSelect = jest.fn();
function setup(isPinned = false) {
  render(
    <ChatHistoryItem
      item={{ ...item, isPinned }}
      selected={false}
      onSelect={onSelect}
      onUpdated={onUpdated}
      onDeleted={onDeleted}
      onError={onError}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Options for Original' }));
}
beforeEach(() => jest.clearAllMocks());

test('pin menu updates only its conversation without navigating', async () => {
  (api.updateChatSessionPin as jest.Mock).mockResolvedValue({
    ...item,
    isPinned: true,
  });
  setup();
  fireEvent.click(await screen.findByRole('menuitem', { name: /Pin/ }));
  await waitFor(() =>
    expect(onUpdated).toHaveBeenCalledWith(
      expect.objectContaining({ isPinned: true }),
    ),
  );
  expect(api.updateChatSessionPin).toHaveBeenCalledWith(item.id, true);
  expect(onSelect).not.toHaveBeenCalled();
});

test('rename trims the title and preserves the pinned state', async () => {
  (api.updateChatSessionTitle as jest.Mock).mockResolvedValue({
    ...item,
    title: 'Renamed',
    isPinned: true,
  });
  setup(true);
  fireEvent.click(await screen.findByRole('menuitem', { name: /Rename/ }));
  fireEvent.change(await screen.findByRole('textbox', { name: 'Chat title' }), {
    target: { value: ' Renamed ' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }));
  await waitFor(() =>
    expect(api.updateChatSessionTitle).toHaveBeenCalledWith(item.id, 'Renamed'),
  );
});

test('delete waits for confirmation and reports failure without removing the row', async () => {
  (api.deleteChatSession as jest.Mock).mockRejectedValue(
    new Error('Stop the active turn first'),
  );
  setup();
  fireEvent.click(await screen.findByRole('menuitem', { name: /Delete/ }));
  expect(api.deleteChatSession).not.toHaveBeenCalled();
  fireEvent.click(
    await screen.findByRole('button', { name: 'Delete', exact: true }),
  );
  expect(await screen.findByText('Stop the active turn first')).toBeVisible();
  expect(onDeleted).not.toHaveBeenCalled();
});

test('confirmed deletion removes only its conversation', async () => {
  (api.deleteChatSession as jest.Mock).mockResolvedValue(undefined);
  setup();
  fireEvent.click(await screen.findByRole('menuitem', { name: /Delete/ }));
  fireEvent.click(
    await screen.findByRole('button', { name: 'Delete', exact: true }),
  );
  await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
  expect(api.deleteChatSession).toHaveBeenCalledWith(item.id);
});
