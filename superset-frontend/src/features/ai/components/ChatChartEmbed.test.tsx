/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { render, screen } from 'spec/helpers/testing-library';
import ChatChartEmbed from './ChatChartEmbed';

jest.mock('@superset-ui/core', () => {
  const actual = jest.requireActual('@superset-ui/core');
  return {
    ...actual,
    StatefulChart: ({
      chartId,
      formData,
    }: {
      chartId?: number;
      formData?: Record<string, unknown>;
    }) => (
      <div data-test="stateful-chart">
        {chartId ? `chart:${chartId}` : `form:${formData?.viz_type}`}
      </div>
    ),
  };
});

// eslint-disable-next-line no-restricted-globals -- TODO: Migrate from describe blocks
describe('ChatChartEmbed', () => {
  test('renders StatefulChart with slice_id', () => {
    render(
      <ChatChartEmbed
        chart={{
          id: 'chart-0',
          title: 'Revenue',
          viz_type: 'pie',
          slice_id: 42,
          form_data: { viz_type: 'pie' },
          explore_url: '/explore/?slice_id=42',
        }}
      />,
    );

    expect(screen.getByText('Revenue')).toBeInTheDocument();
    expect(screen.getByTestId('stateful-chart')).toHaveTextContent('chart:42');
    expect(screen.getByText('Open in Explore')).toBeInTheDocument();
    expect(screen.getByText('Open in Explore').closest('a')).toHaveAttribute(
      'href',
      expect.stringContaining('/explore/?slice_id=42'),
    );
  });

  test('renders StatefulChart with form_data when no slice_id', () => {
    render(
      <ChatChartEmbed
        chart={{
          id: 'chart-0',
          viz_type: 'bar',
          form_data: { viz_type: 'bar', datasource: '1__table' },
        }}
      />,
    );

    expect(screen.getByTestId('stateful-chart')).toHaveTextContent('form:bar');
  });
});
