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
import { fireEvent, render, screen } from 'spec/helpers/testing-library';
import ChatComposer from './ChatComposer';

const props = {
  value: 'Show revenue',
  onChange: jest.fn(),
  models: [
    {
      id: 'text',
      name: 'Text model',
      connection: 'Local',
      vision: false,
      default: true,
    },
    {
      id: 'vision',
      name: 'Vision model',
      connection: 'Hosted',
      vision: true,
      default: false,
    },
  ],
  modelId: 'text',
  onModelChange: jest.fn(),
  images: [],
  onImagesChange: jest.fn(),
  imageLimits: { count: 4, bytes: 5242880 },
  retainedImageCount: 0,
  busy: false,
  running: false,
  onSend: jest.fn(),
  onStop: jest.fn(),
  onError: jest.fn(),
};
beforeEach(() => jest.clearAllMocks());
test('composer sends on Enter but preserves Shift Enter and composition', () => {
  render(<ChatComposer {...props} />);
  const input = screen.getByRole('textbox', { name: 'Message' });
  fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
  fireEvent.keyDown(input, { key: 'Enter', isComposing: true });
  expect(props.onSend).not.toHaveBeenCalled();
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(props.onSend).toHaveBeenCalledTimes(1);
});
test('unavailable selection blocks submission and asks for a replacement', () => {
  render(<ChatComposer {...props} modelId="removed" />);
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  expect(
    screen.getByText('Choose an available model to continue.'),
  ).toBeVisible();
});
test('active execution retains steering and stop while freezing model selection', () => {
  render(<ChatComposer {...props} running />);
  expect(screen.getByRole('button', { name: 'Chat model' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Add attachment' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
  expect(props.onStop).toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'Send guidance' })).toBeEnabled();
});
test('pending uploads block Send and report their progress', () => {
  render(
    <ChatComposer
      {...props}
      modelId="vision"
      images={[
        {
          key: 'upload',
          file: new File(['test'], 'test.png', { type: 'image/png' }),
          preview: 'blob:test',
        },
      ]}
    />,
  );
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  expect(screen.getByText('Uploading...')).toBeVisible();
});
test('attachment menu contains only images and disables them for text models', async () => {
  render(<ChatComposer {...props} />);
  fireEvent.click(screen.getByRole('button', { name: 'Add attachment' }));
  expect(
    await screen.findByRole('menuitem', { name: /Attach images/ }),
  ).toHaveAttribute('aria-disabled', 'true');
  expect(screen.getAllByRole('menuitem')).toHaveLength(1);
});

test('model menu shows clean labels and selects a model without a search input', async () => {
  render(<ChatComposer {...props} />);
  const trigger = screen.getByRole('button', { name: 'Chat model' });
  expect(trigger).toHaveTextContent('Text model');
  fireEvent.click(trigger);
  const vision = await screen.findByRole('menuitem', { name: 'Vision model' });
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  fireEvent.click(vision);
  expect(props.onModelChange).toHaveBeenCalledWith('vision');
});

test('model menu blocks text-only models when the conversation contains images', async () => {
  render(<ChatComposer {...props} modelId="vision" retainedImageCount={1} />);
  fireEvent.click(screen.getByRole('button', { name: 'Chat model' }));
  expect(
    await screen.findByRole('menuitem', { name: 'Text model' }),
  ).toHaveAttribute('aria-disabled', 'true');
});

test('confirmation menu offers ask and full access during a running turn', async () => {
  const change = jest.fn();
  render(
    <ChatComposer
      {...props}
      running
      approvalMode="ask"
      onApprovalModeChange={change}
    />,
  );
  fireEvent.click(
    screen.getByRole('button', {
      name: 'Action approval mode: Ask for approval',
    }),
  );
  fireEvent.click(
    await screen.findByText('Full access', { selector: 'strong' }),
  );
  expect(change).toHaveBeenCalledWith('full_access');
});
