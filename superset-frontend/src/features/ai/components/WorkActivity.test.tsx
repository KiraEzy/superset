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
import WorkActivity from './WorkActivity';

test('shows a formatted duration with tool details hidden until expanded', () => {
  render(
    <WorkActivity
      activity={{
        duration_seconds: 524.9,
        status: 'completed',
        items: [
          {
            id: '1',
            kind: 'tool',
            status: 'completed',
            payload: {
              tool: 'focalbi__health_check_f601bedc6e',
              result: { status: 'healthy' },
            },
          },
        ],
      }}
    />,
  );
  const header = screen.getByText('Worked for 8m 44s');
  expect(screen.getByText(/Called health_check/)).not.toBeVisible();
  fireEvent.click(header);
  expect(screen.getByText(/Called health_check/)).toBeVisible();
  expect(screen.queryByText(/Thinking/)).not.toBeInTheDocument();
});
test('shows provider summaries and thinking status only when recorded', () => {
  render(
    <WorkActivity
      activity={{
        duration_seconds: 2,
        status: 'completed',
        items: [
          {
            id: '1',
            kind: 'reasoning_status',
            status: 'completed',
            payload: {},
          },
          {
            id: '2',
            kind: 'reasoning_summary',
            status: 'completed',
            payload: { message: 'Checked the selected dataset.' },
          },
        ],
      }}
    />,
  );
  fireEvent.click(screen.getByText('Worked for 0m 2s'));
  expect(screen.getByText('Thinking completed')).toBeVisible();
  expect(screen.getByText('Checked the selected dataset.')).toBeVisible();
});
test('waiting states do not imply active execution and missing duration is not invented', () => {
  const { rerender } = render(
    <WorkActivity
      activity={{ duration_seconds: 12, status: 'waiting_approval', items: [] }}
    />,
  );
  expect(screen.getByText('Waiting for input')).toBeVisible();
  rerender(
    <WorkActivity
      activity={{ duration_seconds: null, status: 'completed', items: [] }}
    />,
  );
  expect(screen.getByText('Work details')).toBeVisible();
});

test('live activity opens automatically and user choice survives updates', () => {
  const activity = {
    duration_seconds: 1,
    status: 'running',
    items: [
      {
        id: 'phase',
        kind: 'reasoning_status',
        status: 'running',
        payload: { generation_id: 'g1' },
      },
      {
        id: 'summary',
        kind: 'reasoning_summary',
        status: 'running',
        payload: { generation_id: 'g1', message: 'Checking datasets' },
      },
    ],
  };
  const { rerender } = render(<WorkActivity activity={activity} />);
  expect(screen.getByText('Checking datasets')).toBeVisible();
  fireEvent.click(screen.getByText(/Working/));
  expect(screen.getByText('Checking datasets')).not.toBeVisible();
  rerender(<WorkActivity activity={{ ...activity, duration_seconds: 2 }} />);
  expect(screen.getByText('Checking datasets')).not.toBeVisible();
  fireEvent.click(screen.getByText(/Working/));
  rerender(<WorkActivity activity={{ ...activity, status: 'completed' }} />);
  expect(screen.getByText('Checking datasets')).toBeVisible();
});

test('automatically opened panel collapses on completion', () => {
  const { rerender } = render(
    <WorkActivity
      activity={{ duration_seconds: 1, status: 'running', items: [] }}
    />,
  );
  expect(screen.getByText('No additional activity recorded.')).toBeVisible();
  rerender(
    <WorkActivity
      activity={{ duration_seconds: 2, status: 'completed', items: [] }}
    />,
  );
  expect(
    screen.getByText('No additional activity recorded.'),
  ).not.toBeVisible();
});

test('a remembered user override keeps historical activity open after remount', () => {
  render(
    <WorkActivity
      openOverride
      activity={{ duration_seconds: 2, status: 'completed', items: [] }}
    />,
  );
  expect(screen.getByText('No additional activity recorded.')).toBeVisible();
});

test('interrupted thinking and failed tools never claim completion', () => {
  render(
    <WorkActivity
      openOverride
      activity={{
        duration_seconds: 2,
        status: 'failed',
        items: [
          {
            id: 'p',
            kind: 'reasoning_status',
            status: 'interrupted',
            payload: {},
          },
          {
            id: 't',
            kind: 'tool',
            status: 'failed',
            payload: { tool: 'list_datasets' },
          },
        ],
      }}
    />,
  );
  expect(screen.getByText('Thinking interrupted')).toBeVisible();
  expect(screen.getByText('Failed')).toBeVisible();
  expect(screen.queryByText('Thinking completed')).not.toBeInTheDocument();
});

test('summary text grows in place while phase order and disclosure stay stable', () => {
  const phase = {
    id: 'phase',
    kind: 'reasoning_status',
    status: 'running',
    payload: { generation_id: 'g1' },
  };
  const summary = {
    id: 'summary',
    kind: 'reasoning_summary',
    status: 'running',
    payload: { generation_id: 'g1', message: 'Checking' },
  };
  const activity = {
    duration_seconds: 1,
    status: 'running',
    items: [phase, summary],
  };
  const { rerender } = render(<WorkActivity activity={activity} />);
  const disclosure = screen.getByText(/Working/).closest('details');
  rerender(
    <WorkActivity
      activity={{
        ...activity,
        items: [
          phase,
          {
            ...summary,
            payload: {
              ...summary.payload,
              message: 'Checking datasets and filters',
            },
          },
        ],
      }}
    />,
  );
  expect(screen.getByText('Checking datasets and filters')).toBeVisible();
  expect(screen.getByText(/Working/).closest('details')).toBe(disclosure);
  expect(
    screen.queryByText('Checking', { exact: true }),
  ).not.toBeInTheDocument();
});

test('opted-in model reasoning streams separately from public summaries', () => {
  render(
    <WorkActivity
      activity={{
        duration_seconds: 1,
        status: 'running',
        items: [
          {
            id: 'p',
            kind: 'reasoning_status',
            status: 'running',
            payload: { generation_id: 'g' },
          },
          {
            id: 'r',
            kind: 'model_reasoning',
            status: 'running',
            payload: {
              generation_id: 'g',
              message: 'Inspecting permitted datasets.',
            },
          },
        ],
      }}
    />,
  );
  expect(screen.getByText('Model reasoning: Running')).toBeVisible();
  expect(screen.getByText('Inspecting permitted datasets.')).toBeVisible();
  expect(
    screen.queryByText('No public reasoning summary provided.'),
  ).not.toBeInTheDocument();
});

test('thinking without visible text has no empty disclosure', () => {
  render(
    <WorkActivity
      activity={{
        duration_seconds: 1,
        status: 'running',
        items: [
          { id: 'p', kind: 'reasoning_status', status: 'running', payload: {} },
        ],
      }}
    />,
  );
  expect(
    screen
      .getByText(/Thinking/)
      .closest('details')
      ?.querySelector('summary')?.textContent,
  ).toMatch(/Working/);
  expect(
    screen.queryByText('No public reasoning summary provided.'),
  ).not.toBeInTheDocument();
});
