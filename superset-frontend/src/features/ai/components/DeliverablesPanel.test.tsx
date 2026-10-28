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
import DeliverablesPanel from './DeliverablesPanel';
import { Artifact, PresentedDeliverable } from '../runtime';

const chart: Artifact = {
  id: 'chart',
  type: 'chart',
  title: 'Population chart',
  saved: true,
  version: 1,
  payload: { slice_id: 12 },
  provenance: { connection_id: 'focalbi' },
};
const dashboard: Artifact = {
  id: 'dashboard',
  type: 'dashboard',
  title: 'District dashboard',
  saved: true,
  version: 1,
  payload: { id: 20 },
  provenance: { connection_id: 'focalbi' },
};
const registration = (artifact: Artifact): PresentedDeliverable => ({
  key: artifact.type,
  artifact_id: artifact.id,
  title: artifact.title,
  type: artifact.type as PresentedDeliverable['type'],
  version: 1,
  saved: artifact.saved,
  available: true,
});
const entries = [registration(chart), registration(dashboard)];
const visual = jest.fn((artifact: Artifact) => (
  <div>{`Visual: ${artifact.title}`}</div>
));
const props = {
  entries,
  artifacts: [chart, dashboard],
  selectedKey: null,
  onSelect: jest.fn(),
  renderArtifact: visual,
};

beforeEach(() => jest.clearAllMocks());

test('defaults to one same-origin dashboard iframe and loads no unselected charts', () => {
  render(<DeliverablesPanel {...props} />);
  expect(screen.getByTitle(dashboard.title)).toHaveAttribute(
    'src',
    `${window.location.origin}/superset/dashboard/20/?standalone=2`,
  );
  expect(screen.getByRole('link', { name: 'Open dashboard' })).toHaveAttribute(
    'href',
    '/superset/dashboard/20/',
  );
  expect(visual).not.toHaveBeenCalled();
  expect(document.querySelectorAll('iframe')).toHaveLength(1);
});

test('keeps a selected chart visible while another result is added or updated', () => {
  const { rerender } = render(
    <DeliverablesPanel {...props} selectedKey="chart" />,
  );
  expect(screen.getByText('Visual: Population chart')).toBeVisible();
  const changed = { ...dashboard, id: 'dashboard-updated' };
  rerender(
    <DeliverablesPanel
      {...props}
      selectedKey="chart"
      entries={[entries[0], registration(changed)]}
      artifacts={[chart, changed]}
    />,
  );
  expect(screen.getByText('Visual: Population chart')).toBeVisible();
  expect(document.querySelector('iframe')).toBeNull();
  expect(screen.getByRole('status')).toHaveTextContent(
    '1 new or updated results',
  );
});

test('does not mount inaccessible visuals or arbitrary iframe URLs', () => {
  const { rerender } = render(
    <DeliverablesPanel
      {...props}
      entries={[{ ...entries[0], available: false }]}
      selectedKey="chart"
    />,
  );
  expect(screen.getByText(/no longer have permission/)).toBeVisible();
  expect(visual).not.toHaveBeenCalled();
  rerender(
    <DeliverablesPanel
      {...props}
      artifacts={[{ ...dashboard, payload: { id: 'https://evil.test' } }]}
    />,
  );
  expect(document.querySelector('iframe')).toBeNull();
  expect(
    screen.getByText('This dashboard cannot be displayed here.'),
  ).toBeVisible();
});

test('shows completed unsaved tables as previews and reports missing artifacts', () => {
  const table = {
    ...chart,
    id: 'table',
    type: 'table',
    saved: false,
    title: 'Final totals',
  };
  const { rerender } = render(
    <DeliverablesPanel
      {...props}
      entries={[registration(table)]}
      artifacts={[table]}
    />,
  );
  expect(screen.getByText('Visual: Final totals')).toBeVisible();
  expect(screen.getByText('Preview', { selector: '.ant-tag' })).toBeVisible();
  rerender(
    <DeliverablesPanel
      {...props}
      entries={[registration(table)]}
      artifacts={[]}
    />,
  );
  expect(screen.getByText(/no longer have permission/)).toBeVisible();
});

test('dashboard errors retain an Open dashboard recovery action', async () => {
  render(<DeliverablesPanel {...props} />);
  const frame = screen.getByTitle(dashboard.title) as HTMLIFrameElement;
  frame.contentDocument!.open();
  frame.contentDocument!.write('<!doctype html><title>403 Forbidden</title>');
  frame.contentDocument!.close();
  expect(frame.contentDocument!.title).toBe('403 Forbidden');
  fireEvent.load(frame);
  expect(await screen.findByText(/could not be displayed/)).toBeVisible();
  expect(screen.getByRole('link', { name: 'Open dashboard' })).toBeVisible();
});

test('empty sessions show a helpful explanation without a viewer', () => {
  render(<DeliverablesPanel {...props} entries={[]} artifacts={[]} />);
  expect(
    screen.getByText(/Completed charts, dashboards and visual results/),
  ).toBeVisible();
  expect(document.querySelector('iframe')).toBeNull();
});
