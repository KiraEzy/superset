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

import { styled } from '@apache-superset/core/theme';

import { t } from '@apache-superset/core/translation';

import { Alert } from '@apache-superset/core/components';

import { Button, Input, Select } from '@superset-ui/core/components';

import { Icons } from '@superset-ui/core/components/Icons';

import {
  catalogRequest,
  waitVerification,
  ModelCatalogue as Catalogue,
} from '../modelCatalog';

const Panel = styled.section`
  padding: 24px;

  min-width: 0;

  background: ${({ theme }) => theme.colorBgContainer};

  align-self: start;

  position: sticky;

  top: 12px;

  h3 {
    margin: 0 0 8px;
  }

  .model-lists {
    display: grid;

    grid-template-columns: minmax(0, 1fr) 40px minmax(0, 1fr);

    gap: 8px;

    margin: 20px 0;
  }

  .model-list {
    display: flex;

    flex-direction: column;

    min-width: 0;
  }

  .model-list > label {
    font-weight: 600;

    margin-bottom: 8px;
  }

  .list {
    height: 360px;

    overflow: auto;

    border: 1px solid ${({ theme }) => theme.colorBorder};

    border-radius: ${({ theme }) => theme.borderRadius}px;

    padding: 4px;
  }

  .model-row {
    display: flex;

    gap: 8px;

    padding: 10px 6px;

    cursor: pointer;

    align-items: start;
  }

  .model-row > span {
    min-width: 0;

    overflow-wrap: anywhere;
  }

  small {
    display: block;

    color: ${({ theme }) => theme.colorTextSecondary};
  }

  .arrows {
    display: flex;

    flex-direction: column;

    gap: 8px;

    justify-content: center;
  }

  .catalog-actions {
    display: flex;

    gap: 8px;

    margin-top: 16px;

    flex-wrap: wrap;

    align-items: center;
  }

  @media (max-width: 600px) {
    padding: 16px;

    .model-lists {
      grid-template-columns: minmax(0, 1fr);
    }

    .arrows {
      flex-direction: row;
    }

    .list {
      height: 220px;
    }
  }
`;

export default function ModelCatalogue({
  data,

  reload,
}: {
  data: Catalogue;

  reload: () => Promise<void>;
}) {
  const [draftIds, setIds] = useState<string[]>(() =>
    data.models
      .filter(m => m.published)
      .sort((a, b) => (a.position ?? 0) - (b.position ?? 0))
      .map(m => m.id),
  );

  const [defaultId, setDefaultId] = useState(
    () => data.models.find(m => m.default)?.id ?? '',
  );

  const [left, setLeft] = useState<string[]>([]);

  const [right, setRight] = useState<string[]>([]);

  const [search, setSearch] = useState('');

  const [busy, setBusy] = useState(false);

  const [status, setStatus] = useState('');

  const [error, setError] = useState('');

  const ids = draftIds.filter(id => data.models.some(m => m.id === id));
  const selected = data.models

    .filter(m => ids.includes(m.id))

    .sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));

  const toggle = (values: string[], id: string) =>
    values.includes(id) ? values.filter(v => v !== id) : [...values, id];

  const run = async (action: () => Promise<void>) => {
    setBusy(true);

    setError('');

    try {
      await action();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : t('Model update failed'),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel aria-label={t('Chat model availability')}>
      <h3>{t('Models available in Chat')}</h3>

      <p>
        {t(
          'Verify models, move them to the right, then save availability. Connection discovery alone does not verify each model.',
        )}
      </p>

      {error && <Alert type="error" showIcon message={error} />}

      {status && <p role="status">{status}</p>}

      <Input
        aria-label={t('Search discovered models')}
        placeholder={t('Search models or connections')}
        value={search}
        onChange={e => setSearch(e.target.value)}
      />

      <div className="model-lists">
        <div className="model-list">
          <label>{t('Discovered models')}</label>

          <div
            className="list"
            role="group"
            aria-label={t('Discovered models')}
          >
            {data.models

              .filter(
                m =>
                  !ids.includes(m.id) &&
                  `${m.name} ${m.connection}`

                    .toLowerCase()

                    .includes(search.toLowerCase()),
              )

              .map(m => (
                <label className="model-row" key={m.id}>
                  <input
                    type="checkbox"
                    disabled={busy || m.status === 'unavailable'}
                    checked={left.includes(m.id)}
                    onChange={() => setLeft(toggle(left, m.id))}
                  />

                  <span>
                    {m.name}

                    <small>
                      {m.connection} / {m.status}
                      {m.vision ? ` / ${t('Images')}` : ''}
                    </small>
                  </span>
                </label>
              ))}

            {!data.models.length && (
              <p>{t('Verify a connection to discover its models.')}</p>
            )}
          </div>
        </div>

        <div className="arrows">
          <Button
            aria-label={t('Verify and add selected models')}
            title={t('Verify and add selected models')}
            disabled={busy || !left.length}
            onClick={() =>
              run(async () => {
                for (const id of left) {
                  if (!data.models.find(m => m.id === id)?.ready) {
                    const job = await catalogRequest<{ id: string }>(
                      `${id}/verify`,

                      {},
                    );

                    await waitVerification(job.id, setStatus);
                  }
                }

                setIds(values => [...new Set([...values, ...left])]);

                setLeft([]);

                await reload();
              })
            }
          >
            <Icons.RightOutlined />
          </Button>

          <Button
            aria-label={t('Remove selected models from Chat')}
            title={t('Remove selected models from Chat')}
            disabled={busy || !right.length}
            onClick={() => {
              setIds(ids.filter(id => !right.includes(id)));

              if (right.includes(defaultId)) setDefaultId('');

              setRight([]);
            }}
          >
            <Icons.CaretLeftOutlined />
          </Button>
        </div>

        <div className="model-list">
          <label>{t('Available in Chat')}</label>

          <div
            className="list"
            role="group"
            aria-label={t('Available in Chat')}
          >
            {selected.map(m => (
              <label className="model-row" key={m.id}>
                <input
                  type="checkbox"
                  disabled={busy}
                  checked={right.includes(m.id)}
                  onChange={() => setRight(toggle(right, m.id))}
                />

                <span>
                  {m.name}

                  <small>
                    {m.connection} /{' '}
                    {m.ready ? m.status : t('Needs verification')}
                    {m.vision ? ` / ${t('Images')}` : ''}
                  </small>
                </span>
              </label>
            ))}
          </div>
        </div>
      </div>

      <label>{t('Default model')}</label>

      <Select
        ariaLabel={t('Default model')}
        value={defaultId || undefined}
        onChange={value => setDefaultId(String(value))}
        options={selected.map(m => ({
          value: m.id,

          label: `${m.name} / ${m.connection}`,
        }))}
        css={{ width: '100%' }}
      />

      <div className="catalog-actions">
        <Button
          disabled={busy || right.length !== 1 || ids.indexOf(right[0]) <= 0}
          onClick={() => {
            const next = [...ids];

            const i = next.indexOf(right[0]);

            [next[i - 1], next[i]] = [next[i], next[i - 1]];

            setIds(next);
          }}
        >
          {t('Move up')}
        </Button>

        <Button
          disabled={
            busy ||
            right.length !== 1 ||
            ids.indexOf(right[0]) === ids.length - 1
          }
          onClick={() => {
            const next = [...ids];

            const i = next.indexOf(right[0]);

            [next[i + 1], next[i]] = [next[i], next[i + 1]];

            setIds(next);
          }}
        >
          {t('Move down')}
        </Button>

        <Button
          type="primary"
          loading={busy}
          disabled={!ids.length || !defaultId || selected.some(m => !m.ready)}
          onClick={() =>
            run(async () => {
              await catalogRequest('publish', { ids, default: defaultId });

              await reload();

              setStatus(t('Model availability saved.'));
            })
          }
        >
          {t('Save model availability')}
        </Button>
      </div>
    </Panel>
  );
}
