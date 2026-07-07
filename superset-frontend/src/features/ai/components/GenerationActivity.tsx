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
import { useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { styled, css } from '@apache-superset/core/theme';
import { Icons } from '@superset-ui/core/components/Icons';
import { GenerationActivityEntry } from 'src/features/ai/types';

const ActivityWrapper = styled.div`
  ${({ theme }) => css`
    margin-bottom: ${theme.sizeUnit * 2}px;
    font-size: ${theme.fontSizeSM}px;
    color: ${theme.colorTextSecondary};
  `}
`;

const ActivityToggle = styled.button`
  ${({ theme }) => css`
    display: flex;
    align-items: center;
    gap: ${theme.sizeUnit}px;
    padding: 0;
    border: none;
    background: none;
    color: ${theme.colorTextSecondary};
    font-size: ${theme.fontSizeSM}px;
    cursor: pointer;

    &:hover {
      color: ${theme.colorText};
    }
  `}
`;

const ActivityList = styled.ul`
  ${({ theme }) => css`
    margin: ${theme.sizeUnit}px 0 0;
    padding: 0 0 0 ${theme.sizeUnit * 3}px;
    list-style: none;
  `}
`;

const ActivityItem = styled.li`
  ${({ theme }) => css`
    font-style: italic;
    line-height: 1.5;
    color: ${theme.colorTextSecondary};

    & + & {
      margin-top: ${theme.sizeUnit * 0.5}px;
    }
  `}
`;

const ActivityTime = styled.span`
  ${({ theme }) => css`
    margin-right: ${theme.sizeUnit}px;
    font-style: normal;
    color: ${theme.colorTextTertiary};
    font-size: ${theme.fontSizeSM - 1}px;
  `}
`;

function formatActivityTime(at: string): string {
  const parsed = Date.parse(at);
  if (Number.isNaN(parsed)) {
    return '';
  }
  return new Date(parsed).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

interface GenerationActivityProps {
  activity?: GenerationActivityEntry[];
  status?: string;
}

export default function GenerationActivity({
  activity,
  status,
}: GenerationActivityProps) {
  const [expanded, setExpanded] = useState(true);
  const entries = activity ?? [];
  const hasEntries = entries.length > 0;

  if (!hasEntries && !status) {
    return null;
  }

  return (
    <ActivityWrapper>
      {hasEntries ? (
        <>
          <ActivityToggle
            type="button"
            onClick={() => setExpanded(prev => !prev)}
            aria-expanded={expanded}
          >
            {expanded ? (
              <Icons.DownOutlined iconSize="xs" />
            ) : (
              <Icons.RightOutlined iconSize="xs" />
            )}
            {t('Activity (%s)', entries.length)}
          </ActivityToggle>
          {expanded && (
            <ActivityList>
              {entries.map((entry, index) => (
                <ActivityItem key={`${entry.at}-${index}`}>
                  {entry.at && (
                    <ActivityTime>{formatActivityTime(entry.at)}</ActivityTime>
                  )}
                  {entry.message}
                </ActivityItem>
              ))}
            </ActivityList>
          )}
        </>
      ) : (
        status && <ActivityItem>{status}</ActivityItem>
      )}
    </ActivityWrapper>
  );
}
