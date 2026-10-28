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
  within,
} from 'spec/helpers/testing-library';
import DeliverableLinks from './DeliverableLinks';
import { Artifact } from '../runtime';

const saved: Artifact = {
  id: 'chart',
  type: 'chart',
  title: 'Passenger journeys',
  saved: true,
  version: 1,
  payload: { slice_id: 12 },
  provenance: { connection_id: 'focalbi' },
};
const sql: Artifact = {
  ...saved,
  id: 'sql',
  type: 'sql',
  title: 'SQL query',
  payload: { sql: 'SELECT 1' },
};

test('shows saved links immediately, updates inspection and keeps work details collapsed', () => {
  const onInspect = jest.fn();
  const { rerender } = render(
    <DeliverableLinks artifacts={[saved, sql]} onInspect={onInspect} />,
  );
  expect(screen.getByRole('link', { name: saved.title })).toHaveAttribute(
    'href',
    '#ai-chat-deliverables',
  );
  expect(screen.getByText('Inspect SQL query')).not.toBeVisible();
  fireEvent.click(screen.getByText('Work details (1)'));
  expect(screen.getByText('Inspect SQL query')).toBeVisible();
  fireEvent.click(screen.getByText('Inspect SQL query'));
  expect(onInspect).toHaveBeenLastCalledWith('sql');
  const updated = { ...saved, id: 'updated', title: 'Updated journeys' };
  rerender(
    <DeliverableLinks
      artifacts={[saved, sql, updated]}
      onInspect={onInspect}
    />,
  );
  const section = screen.getByRole('region', { name: 'Deliverables' });
  expect(within(section).getAllByRole('listitem')).toHaveLength(1);
  fireEvent.click(
    within(section).getByRole('button', { name: 'View Updated journeys' }),
  );
  expect(onInspect).toHaveBeenLastCalledWith('updated');
});

test('preview-only and empty replies never claim a saved deliverable', () => {
  const { rerender, container } = render(
    <DeliverableLinks
      artifacts={[
        { ...saved, saved: false, payload: { form_data_key: 'preview' } },
      ]}
      onInspect={jest.fn()}
    />,
  );
  expect(
    screen.queryByRole('region', { name: 'Deliverables' }),
  ).not.toBeInTheDocument();
  expect(screen.getByText('Work details (1)')).toBeVisible();
  rerender(<DeliverableLinks artifacts={[]} onInspect={jest.fn()} />);
  expect(container).toBeEmptyDOMElement();
});

test('retired saved resources move into work details instead of reappearing as deliverables', () => {
  const onInspect = jest.fn();
  render(
    <DeliverableLinks
      artifacts={[saved]}
      presentations={[]}
      onInspect={onInspect}
    />,
  );
  expect(
    screen.queryByRole('region', { name: 'Deliverables' }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByText('Work details (1)'));
  fireEvent.click(
    screen.getByRole('button', { name: 'Inspect Passenger journeys' }),
  );
  expect(onInspect).toHaveBeenCalledWith(saved.id);
});
