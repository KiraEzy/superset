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
import { Component, ReactNode, useState } from 'react';
import { styled, css } from '@apache-superset/core/theme';
import { t } from '@apache-superset/core/translation';
import { StatefulChart, QueryFormData } from '@superset-ui/core';
import { AiChatChartPayload } from 'src/features/ai/types';
import { rewriteSupersetExploreUrl } from 'src/features/ai/supersetUrlUtils';

const ChartCard = styled.div`
  ${({ theme }) => css`
    width: 100%;
    min-height: 280px;
    margin: ${theme.sizeUnit * 2}px 0;
    border: 1px solid ${theme.colorBorderSecondary};
    border-radius: ${theme.borderRadiusLG}px;
    overflow: hidden;
    background: ${theme.colorBgContainer};
  `}
`;

const ChartHeader = styled.div`
  ${({ theme }) => css`
    padding: ${theme.sizeUnit * 2}px ${theme.sizeUnit * 3}px;
    border-bottom: 1px solid ${theme.colorBorderSecondary};
    font-size: ${theme.fontSizeSM}px;
    font-weight: 600;
    color: ${theme.colorText};
  `}
`;

const ChartBody = styled.div`
  min-height: 280px;
`;

const ChartFooter = styled.div`
  ${({ theme }) => css`
    padding: ${theme.sizeUnit * 2}px ${theme.sizeUnit * 3}px;
    border-top: 1px solid ${theme.colorBorderSecondary};
    font-size: ${theme.fontSizeSM}px;

    a {
      color: ${theme.colorPrimary};
      text-decoration: none;
      &:hover {
        text-decoration: underline;
      }
    }
  `}
`;

const FallbackText = styled.div`
  ${({ theme }) => css`
    padding: ${theme.sizeUnit * 4}px;
    color: ${theme.colorTextSecondary};
    font-size: ${theme.fontSizeSM}px;
  `}
`;

interface ChatChartEmbedProps {
  chart: AiChatChartPayload;
}

class ChartErrorBoundary extends Component<
  { children: ReactNode; onError: () => void },
  { hasError: boolean }
> {
  constructor(props: { children: ReactNode; onError: () => void }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  componentDidCatch(): void {
    this.props.onError();
  }

  render() {
    if (this.state.hasError) {
      return null;
    }
    return this.props.children;
  }
}

export default function ChatChartEmbed({ chart }: ChatChartEmbedProps) {
  const [hasError, setHasError] = useState(false);

  const exploreHref = chart.explore_url
    ? rewriteSupersetExploreUrl(chart.explore_url)
    : undefined;
  const exploreLink = exploreHref ? (
    <a href={exploreHref} target="_blank" rel="noopener noreferrer">
      {t('Open in Explore')}
    </a>
  ) : null;

  if (hasError) {
    return (
      <ChartCard>
        {chart.title && <ChartHeader>{chart.title}</ChartHeader>}
        <FallbackText>
          {t('Unable to render chart preview.')}
          {exploreLink && <> {exploreLink}</>}
        </FallbackText>
      </ChartCard>
    );
  }

  const canRender =
    typeof chart.slice_id === 'number' ||
    (chart.form_data && Object.keys(chart.form_data).length > 0);

  if (!canRender) {
    return null;
  }

  return (
    <ChartCard>
      {chart.title && <ChartHeader>{chart.title}</ChartHeader>}
      <ChartBody>
        <ChartErrorBoundary onError={() => setHasError(true)}>
          {typeof chart.slice_id === 'number' ? (
            <StatefulChart
              chartId={chart.slice_id}
              width="100%"
              height={320}
              showLoading
            />
          ) : (
            <StatefulChart
              formData={chart.form_data as QueryFormData}
              width="100%"
              height={320}
              showLoading
            />
          )}
        </ChartErrorBoundary>
      </ChartBody>
      {exploreLink && <ChartFooter>{exploreLink}</ChartFooter>}
    </ChartCard>
  );
}
