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

import { Button, Progress, Tooltip } from '@superset-ui/core/components';
import { styled, useTheme } from '@apache-superset/core/theme';
import { t } from '@apache-superset/core/translation';
import { ContextUsage } from '../runtime';

const Trigger = styled(Button)`
  flex: 0 0 36px;
  width: 36px;
  min-width: 36px;
  height: 36px;
  padding: 0;
  border: 0;
  border-radius: 18px;
  .ant-progress {
    line-height: 1;
  }
`;
const Details = styled.div`
  min-width: 210px;
  font-variant-numeric: tabular-nums;
  dl {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 6px 16px;
    margin: 10px 0;
  }
  dt,
  dd {
    margin: 0;
  }
  p {
    margin: 4px 0 0;
  }
`;

export default function ContextUsageRing({
  usage,
}: {
  usage?: ContextUsage | null;
}) {
  const theme = useTheme();
  const known = Boolean(usage && usage.context_window_tokens > 0);
  const used = usage ? usage.input_tokens + usage.output_tokens : 0;
  const percent =
    known && usage
      ? Math.min(100, Math.max(0, (used / usage.context_window_tokens) * 100))
      : 0;
  const label = known
    ? t('%s%% context used', Math.round(percent))
    : t('Context usage unavailable');
  const number = (value: number) => value.toLocaleString();
  return (
    <Tooltip
      placement="top"
      trigger={['hover', 'focus', 'click']}
      title={
        <Details>
          <strong>{label}</strong>
          {known && usage ? (
            <>
              <p>
                {t(
                  '%s / %s tokens',
                  number(used),
                  number(usage.context_window_tokens),
                )}
              </p>
              <dl>
                <dt>{t('Input')}</dt>
                <dd>{number(usage.input_tokens)}</dd>
                <dt>{t('Output')}</dt>
                <dd>{number(usage.output_tokens)}</dd>
                <dt>{t('Output limit')}</dt>
                <dd>{number(usage.output_limit_tokens)}</dd>
                <dt>{t('Input allowance')}</dt>
                <dd>{number(usage.input_allowance_tokens)}</dd>
                <dt>{t('Tool result reserve')}</dt>
                <dd>{number(usage.tool_result_reserve_tokens)}</dd>
              </dl>
              <p>
                {usage.estimated
                  ? t('Estimated for the latest model request.')
                  : t('Provider-reported usage for the latest model request.')}
              </p>
            </>
          ) : (
            <p>{t('Usage appears when a model request starts.')}</p>
          )}
        </Details>
      }
    >
      <Trigger buttonStyle="tertiary" aria-label={label}>
        <span aria-hidden="true">
          <Progress
            type="circle"
            size={18}
            percent={percent}
            showInfo={false}
            strokeWidth={12}
            strokeColor={
              percent >= 90 ? theme.colorError : theme.colorTextSecondary
            }
            trailColor={theme.colorBorder}
          />
        </span>
      </Trigger>
    </Tooltip>
  );
}
