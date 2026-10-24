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
import { useState } from 'react';
import { styled } from '@apache-superset/core/theme';
import { t } from '@apache-superset/core/translation';
import { Icons } from '@superset-ui/core/components/Icons';
import { WorkActivityData } from '../runtime';
import ChatMarkdown from './ChatMarkdown';

const Disclosure = styled.details`
  margin: 0 0 12px;
  padding: 0 0 4px;
  border-bottom: 1px solid ${({ theme }) => theme.colorBorderSecondary};
  > summary {
    display: flex;
    align-items: center;
    gap: 4px;
    width: fit-content;
    min-height: 28px;
    cursor: pointer;
    color: ${({ theme }) => theme.colorTextSecondary};
    font-size: ${({ theme }) => theme.fontSizeSM}px;
    list-style: none;
    &::-webkit-details-marker {
      display: none;
    }
  }
  &[open] > summary svg {
    transform: rotate(90deg);
  }
  .work-entry {
    margin: 12px 0;
  }
  .work-entry > summary {
    cursor: pointer;
  }
  pre {
    max-height: 320px;
    overflow: auto;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    margin: 8px 0;
  }
`;

function activityStatus(status: string): string {
  switch (status) {
    case 'running':
      return t('Running');
    case 'completed':
      return t('Completed');
    case 'failed':
      return t('Failed');
    case 'cancelled':
      return t('Cancelled');
    case 'interrupted':
      return t('Interrupted');
    default:
      return status;
  }
}

function ThinkingPhase({
  item,
  summaries,
}: {
  item: WorkActivityData['items'][number];
  summaries: WorkActivityData['items'];
}) {
  const [manualOpen, setManualOpen] = useState<boolean>();
  const open = manualOpen ?? item.status === 'running';
  const label =
    item.status === 'running'
      ? t('Thinking\u2026')
      : item.status === 'completed'
        ? t('Thinking completed')
        : item.status === 'cancelled'
          ? t('Thinking cancelled')
          : t('Thinking interrupted');
  const hasModelReasoning = summaries.some(
    summary => summary.kind === 'model_reasoning',
  );
  if (!summaries.length)
    return (
      <div className="work-entry">
        <span role="status" aria-live="polite">
          {label}
        </span>
      </div>
    );
  return (
    <details className="work-entry" open={open}>
      <summary
        onClick={event => {
          event.preventDefault();
          setManualOpen(!open);
        }}
      >
        <span role="status" aria-live="polite">
          {hasModelReasoning
            ? t('Model reasoning: %s', activityStatus(item.status))
            : label}
        </span>
      </summary>
      {summaries.map(summary => (
        <ChatMarkdown
          key={summary.id}
          content={String(summary.payload.message ?? '')}
        />
      ))}
    </details>
  );
}

export default function WorkActivity({
  activity,
  openOverride,
  onOpenChange,
}: {
  activity?: WorkActivityData;
  openOverride?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const [manualOpen, setManualOpen] = useState<boolean>();
  if (!activity) return null;
  const terminal = ['completed', 'failed', 'cancelled', 'canceled'].includes(
    activity.status,
  );
  const seconds = Math.max(0, Math.floor(activity.duration_seconds ?? 0));
  const title = !terminal
    ? activity.status.startsWith('waiting') ||
      activity.status === 'needs_review'
      ? t('Waiting for input')
      : t('Working\u2026')
    : activity.duration_seconds === null
      ? t('Work details')
      : t('Worked for %sm %ss', Math.floor(seconds / 60), seconds % 60);
  const open = openOverride ?? manualOpen ?? !terminal;
  const phases = new Set(
    activity.items
      .filter(item => item.kind === 'reasoning_status')
      .map(item => item.payload.generation_id)
      .filter(Boolean),
  );
  return (
    <Disclosure open={open}>
      <summary
        onClick={event => {
          event.preventDefault();
          setManualOpen(!open);
          onOpenChange?.(!open);
        }}
      >
        <span role="status" aria-live="polite">
          {title}
        </span>
        <Icons.RightOutlined iconSize="xs" aria-hidden />
      </summary>
      {activity.items.map(item => {
        if (
          ['reasoning_summary', 'model_reasoning'].includes(item.kind) &&
          phases.has(item.payload.generation_id)
        )
          return null;
        if (item.kind === 'reasoning_status')
          return (
            <ThinkingPhase
              key={item.id}
              item={item}
              summaries={activity.items.filter(
                summary =>
                  ['reasoning_summary', 'model_reasoning'].includes(
                    summary.kind,
                  ) &&
                  Boolean(item.payload.generation_id) &&
                  summary.payload.generation_id === item.payload.generation_id,
              )}
            />
          );
        if (item.kind === 'tool')
          return (
            <details className="work-entry" key={item.id}>
              <summary>
                {t(
                  'Called %s',
                  String(item.payload.tool ?? t('tool'))
                    .replace(/^[^_]+__/, '')
                    .replace(/_[a-f0-9]{10}$/, ''),
                )}
                {' \u00b7 '}
                <span role="status" aria-live="polite">
                  {activityStatus(item.status)}
                </span>
              </summary>
              <pre>{JSON.stringify(item.payload, null, 2)}</pre>
            </details>
          );
        return (
          <div className="work-entry" key={item.id}>
            {['reasoning_summary', 'model_reasoning'].includes(item.kind) ? (
              <ChatMarkdown content={String(item.payload.message ?? '')} />
            ) : (
              <span>{String(item.payload.message ?? '')}</span>
            )}
          </div>
        );
      })}
      {!activity.items.length && <p>{t('No additional activity recorded.')}</p>}
    </Disclosure>
  );
}
