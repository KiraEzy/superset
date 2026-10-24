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
import { useEffect, useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { Alert } from '@apache-superset/core/components';
import { Select } from '@superset-ui/core/components';
import {
  fetchMcpAccessOptions,
  McpAccessOptions,
  McpToolAccess,
} from '../aiConnectionConfig';

export default function McpToolAccessEditor({
  value = { roles: {}, users: {} },
  onChange,
}: {
  value?: McpToolAccess;
  onChange?: (value: McpToolAccess) => void;
}) {
  const [options, setOptions] = useState<McpAccessOptions>();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let mounted = true;
    fetchMcpAccessOptions()
      .then(result => {
        if (mounted) setOptions(result);
      })
      .catch(() => {
        if (mounted) setFailed(true);
      });
    return () => {
      mounted = false;
    };
  }, []);
  if (failed)
    return (
      <Alert
        type="error"
        message={t(
          'Tool access options could not load. Reload this page before editing restrictions.',
        )}
      />
    );
  return (
    <div>
      <p>
        {t(
          'These restrictions apply to Chat only and never grant additional Superset permissions. Unlisted users and roles retain their existing permissions. Matching role tool lists are combined; a user-specific list can restrict them further. An empty tool list blocks all BI tools for that rule.',
        )}
      </p>
      {(['roles', 'users'] as const).map(kind => (
        <section key={kind}>
          <p>
            {kind === 'roles'
              ? t('Roles with a Chat tool restriction')
              : t('Users with a Chat tool restriction')}
          </p>
          <Select
            aria-label={
              kind === 'roles' ? t('Restricted roles') : t('Restricted users')
            }
            mode="multiple"
            css={{ width: '100%' }}
            loading={!options}
            disabled={!options}
            value={Object.keys(value[kind])}
            options={[
              ...new Set([
                ...(options?.[kind] ?? []),
                ...Object.keys(value[kind]),
              ]),
            ].map(name => ({ value: name, label: name }))}
            onChange={names =>
              onChange?.({
                ...value,
                [kind]: Object.fromEntries(
                  (names as string[]).map(name => [
                    name,
                    value[kind][name] ?? [],
                  ]),
                ),
              })
            }
          />
          {Object.entries(value[kind]).map(([name, tools]) => (
            <div key={name}>
              <p>{t('Allowed Chat tools for %s', name)}</p>
              <Select
                aria-label={t(
                  'Allowed Chat tools for %s %s',
                  kind === 'roles' ? t('role') : t('user'),
                  name,
                )}
                mode="multiple"
                css={{ width: '100%' }}
                disabled={!options}
                value={tools}
                options={[
                  ...new Set([...(options?.tools ?? []), ...tools]),
                ].map(tool => ({ value: tool, label: tool }))}
                onChange={selected =>
                  onChange?.({
                    ...value,
                    [kind]: { ...value[kind], [name]: selected as string[] },
                  })
                }
                placeholder={t('No BI tools allowed')}
              />
            </div>
          ))}
        </section>
      ))}
      <p>
        <a href="/roles/">{t('Manage role permissions')}</a>
        {' · '}
        <a href="/users/">{t('Manage users and role assignments')}</a>
      </p>
    </div>
  );
}
