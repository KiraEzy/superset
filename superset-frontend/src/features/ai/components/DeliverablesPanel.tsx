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
import { ReactNode, useEffect, useRef, useState } from 'react';
import { styled } from '@apache-superset/core/theme';
import { t } from '@apache-superset/core/translation';
import { Alert } from '@apache-superset/core/components';
import { Loading, Select, Tag } from '@superset-ui/core/components';
import { Artifact, PresentedDeliverable } from '../runtime';

const Viewer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 100%;
  .viewer-actions {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
  iframe {
    width: 100%;
    min-height: 650px;
    flex: 1;
    border: 0;
    background: ${({ theme }) => theme.colorBgContainer};
  }
  .ant-select {
    width: 100%;
    min-width: 0;
  }
`;

function nativeDashboard(artifact?: Artifact): string | undefined {
  const id = artifact?.payload.id;
  if (
    artifact?.type !== 'dashboard' ||
    artifact.provenance?.connection_id !== 'focalbi' ||
    typeof id !== 'number' ||
    !Number.isSafeInteger(id) ||
    id <= 0
  )
    return undefined;
  return `/superset/dashboard/${id}/`;
}

function DashboardView({ url, title }: { url: string; title: string }) {
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const timer = useRef<number | undefined>();
  useEffect(() => {
    timer.current = window.setTimeout(() => {
      setLoading(false);
      setFailed(true);
    }, 30000);
    return () => window.clearTimeout(timer.current);
  }, [url]);
  return (
    <>
      <div className="viewer-actions">
        <a href={url} target="_blank" rel="noopener noreferrer">
          {t('Open dashboard')}
        </a>
      </div>
      {loading && (
        <div role="status" aria-label={t('Loading dashboard')}>
          <Loading position="inline" size="s" />
        </div>
      )}
      {failed && (
        <Alert
          type="warning"
          message={t(
            'The dashboard could not be displayed. Open it to check your access or reload the page.',
          )}
        />
      )}
      <iframe
        src={new URL(`${url}?standalone=2`, window.location.origin).href}
        title={title}
        onError={() => {
          setLoading(false);
          setFailed(true);
        }}
        onLoad={event => {
          const frame = event.currentTarget;
          try {
            const doc = frame.contentDocument;
            const path = frame.contentWindow?.location.pathname ?? '';
            if (path === 'blank' && !/403|404/.test(doc?.title ?? '')) return;
            window.clearTimeout(timer.current);
            setLoading(false);
            setFailed(
              !doc ||
                /\/(login|select_post)/.test(path) ||
                /403|404/.test(doc.title),
            );
          } catch {
            window.clearTimeout(timer.current);
            setLoading(false);
            setFailed(true);
          }
        }}
      />
    </>
  );
}

export default function DeliverablesPanel({
  entries,
  artifacts,
  selectedKey,
  onSelect,
  renderArtifact,
}: {
  entries: PresentedDeliverable[];
  artifacts: Artifact[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
  renderArtifact: (artifact: Artifact) => ReactNode;
}) {
  const selected =
    entries.find(item => item.key === selectedKey) ??
    [...entries].reverse().find(item => item.type === 'dashboard') ??
    entries[entries.length - 1];
  const version = (entry: PresentedDeliverable) =>
    JSON.stringify([entry.artifact_id, entry.version, entry.title]);
  const [seen, setSeen] = useState<Map<string, string> | null>(() =>
    entries.length
      ? new Map(entries.map(entry => [entry.key, version(entry)]))
      : null,
  );
  // Capture the first loaded registry without treating old results as new arrivals.
  if (seen === null && entries.length) {
    setSeen(new Map(entries.map(entry => [entry.key, version(entry)])));
  }
  const updated = new Set(
    entries
      .filter(entry => seen !== null && seen.get(entry.key) !== version(entry))
      .map(entry => entry.key),
  );
  const artifact = artifacts.find(item => item.id === selected?.artifact_id);
  const dashboard = nativeDashboard(artifact);
  return (
    <Viewer>
      <h2>{t('Deliverables')}</h2>
      {entries.length ? (
        <>
          <Select
            aria-label={t('Choose a deliverable')}
            value={selected?.key}
            onChange={(key: string) => {
              onSelect(key);
              const entry = entries.find(value => value.key === key);
              if (entry)
                setSeen(values => {
                  const next = new Map(values ?? []);
                  next.set(key, version(entry));
                  return next;
                });
            }}
            options={entries.map(item => ({
              value: item.key,
              label: `${item.title} | ${item.type === 'dashboard' ? t('Dashboard') : item.type === 'table' ? t('Table') : t('Chart')}${!item.saved ? ` | ${t('Preview')}` : ''}${updated.has(item.key) ? ` | ${t('Updated')}` : ''}`,
            }))}
          />
          {selected && (
            <div className="viewer-actions">
              <Tag>{selected.saved ? t('Saved') : t('Preview')}</Tag>
              {updated.size > 0 && (
                <span role="status">
                  {t('%s new or updated results', updated.size)}
                </span>
              )}
            </div>
          )}
          {!selected?.available || !artifact ? (
            <Alert
              type="warning"
              message={t(
                'This deliverable is unavailable or you no longer have permission to view it.',
              )}
            />
          ) : selected.type === 'dashboard' ? (
            dashboard ? (
              <DashboardView
                key={selected.artifact_id}
                url={dashboard}
                title={selected.title}
              />
            ) : (
              <Alert
                type="info"
                message={t('This dashboard cannot be displayed here.')}
              />
            )
          ) : (
            renderArtifact({
              ...artifact,
              title: selected.title,
              saved: selected.saved,
            })
          )}
        </>
      ) : (
        <p>
          {t(
            'Completed charts, dashboards and visual results will appear here.',
          )}
        </p>
      )}
    </Viewer>
  );
}
