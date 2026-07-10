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
import { useEffect, useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { styled, css } from '@apache-superset/core/theme';
import {
  Button,
  Input,
  InputNumber,
  Typography,
} from '@superset-ui/core/components';
import SubMenu, { SubMenuProps } from 'src/features/home/SubMenu';
import { useToasts } from 'src/components/MessageToasts/withToasts';
import {
  deleteGlobalConfigKey,
  fetchGlobalConfigAdmin,
  saveGlobalConfig,
} from 'src/features/globalConfiguration/api';
import {
  DEFAULT_MCP_JWT_TTL_SECONDS,
  KEY_MCP_JWT_TTL_SECONDS,
  KEY_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX,
  MAX_MCP_JWT_TTL_SECONDS,
  MAX_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX,
  MIN_MCP_JWT_TTL_SECONDS,
  MIN_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX,
} from 'src/features/globalConfiguration/constants';
import type {
  GlobalConfigAdminPayload,
  GlobalConfigRow,
} from 'src/features/globalConfiguration/types';

const StyledContent = styled.div`
  ${({ theme }) => css`
    max-width: 720px;
    margin: 0 ${theme.sizeUnit * 3}px ${theme.sizeUnit * 6}px;
    padding: ${theme.sizeUnit * 6}px;
    background-color: ${theme.colorBgContainer};
  `}
`;

const SectionTitle = styled(Typography.Title)`
  margin-top: ${({ theme }) => theme.sizeUnit * 4}px !important;
`;

const ButtonRow = styled.div`
  ${({ theme }) => css`
    display: flex;
    gap: ${theme.sizeUnit * 2}px;
    margin-top: ${theme.sizeUnit * 4}px;
  `}
`;

const FieldRow = styled.div`
  ${({ theme }) => css`
    display: flex;
    flex-direction: column;
    gap: ${theme.sizeUnit}px;
    margin-bottom: ${theme.sizeUnit * 3}px;
  `}
`;

const RowList = styled.div`
  ${({ theme }) => css`
    display: flex;
    flex-direction: column;
    gap: ${theme.sizeUnit * 2}px;
    margin-top: ${theme.sizeUnit * 2}px;
  `}
`;

const RowItem = styled.div`
  ${({ theme }) => css`
    display: flex;
    align-items: center;
    gap: ${theme.sizeUnit * 2}px;
    padding: ${theme.sizeUnit * 2}px;
    border: 1px solid ${theme.colorBorderSecondary};
    border-radius: ${theme.borderRadius}px;
  `}
`;

const RowKeyValue = styled.div`
  flex: 1;
  min-width: 0;
`;

export default function GlobalConfiguration() {
  const { addSuccessToast, addDangerToast } = useToasts();
  const [loading, setLoading] = useState(true);
  const [savingKnown, setSavingKnown] = useState(false);
  const [addingEntry, setAddingEntry] = useState(false);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);
  const [navbarWidth, setNavbarWidth] = useState<number>(
    MIN_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX,
  );
  const [mcpJwtTtl, setMcpJwtTtl] = useState<number>(
    DEFAULT_MCP_JWT_TTL_SECONDS,
  );
  const [rows, setRows] = useState<GlobalConfigRow[]>([]);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');

  const applyPayload = (payload: GlobalConfigAdminPayload) => {
    setNavbarWidth(
      payload.known[KEY_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX] ??
        MIN_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX,
    );
    setMcpJwtTtl(
      payload.known[KEY_MCP_JWT_TTL_SECONDS] ?? DEFAULT_MCP_JWT_TTL_SECONDS,
    );
    setRows(payload.rows);
  };

  useEffect(() => {
    let cancelled = false;
    fetchGlobalConfigAdmin()
      .then(payload => {
        if (cancelled) return;
        applyPayload(payload);
      })
      .catch(() => {
        addDangerToast(t('Failed to load global configuration.'));
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [addDangerToast]);

  const menuData: SubMenuProps = {
    name: t('Global Configuration'),
  };

  const handleSaveKnown = async () => {
    if (
      navbarWidth < MIN_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX ||
      navbarWidth > MAX_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX
    ) {
      addDangerToast(
        t(
          'Enter a value between %s and %s',
          MIN_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX,
          MAX_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX,
        ),
      );
      return;
    }
    if (
      mcpJwtTtl < MIN_MCP_JWT_TTL_SECONDS ||
      mcpJwtTtl > MAX_MCP_JWT_TTL_SECONDS
    ) {
      addDangerToast(
        t(
          'Enter a value between %s and %s',
          MIN_MCP_JWT_TTL_SECONDS,
          MAX_MCP_JWT_TTL_SECONDS,
        ),
      );
      return;
    }
    try {
      setSavingKnown(true);
      const result = await saveGlobalConfig({
        known: {
          [KEY_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX]: navbarWidth,
          [KEY_MCP_JWT_TTL_SECONDS]: mcpJwtTtl,
        },
      });
      applyPayload(result);
      addSuccessToast(t('Known settings saved.'));
    } catch (error) {
      addDangerToast(
        error instanceof Error && error.message
          ? error.message
          : t('Failed to save known settings.'),
      );
    } finally {
      setSavingKnown(false);
    }
  };

  const handleAddEntry = async () => {
    const key = newKey.trim();
    if (!key) {
      addDangerToast(t('Key is required.'));
      return;
    }
    try {
      setAddingEntry(true);
      const result = await saveGlobalConfig({
        entries: { [key]: newValue },
      });
      applyPayload(result);
      setNewKey('');
      setNewValue('');
      addSuccessToast(t('Entry added.'));
    } catch (error) {
      addDangerToast(
        error instanceof Error && error.message
          ? error.message
          : t('Failed to add entry.'),
      );
    } finally {
      setAddingEntry(false);
    }
  };

  const handleDeleteEntry = async (key: string) => {
    try {
      setDeletingKey(key);
      const result = await deleteGlobalConfigKey(key);
      applyPayload(result);
      addSuccessToast(t('Entry deleted.'));
    } catch (error) {
      addDangerToast(
        error instanceof Error && error.message
          ? error.message
          : t('Failed to delete entry.'),
      );
    } finally {
      setDeletingKey(null);
    }
  };

  return (
    <>
      <SubMenu {...menuData} />
      <StyledContent>
        <Typography.Paragraph type="secondary">
          {t(
            'Manage global application settings. Known settings use typed validation; free-form entries accept arbitrary string keys and values.',
          )}
        </Typography.Paragraph>

        <SectionTitle level={5}>{t('Known settings')}</SectionTitle>

        <FieldRow>
          <Typography.Text>{t('Navbar display name max width (px)')}</Typography.Text>
          <InputNumber
            min={MIN_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX}
            max={MAX_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX}
            precision={0}
            value={navbarWidth}
            disabled={loading}
            style={{ width: '100%' }}
            onChange={value => {
              if (typeof value === 'number') {
                setNavbarWidth(value);
              }
            }}
          />
        </FieldRow>

        <FieldRow>
          <Typography.Text>{t('MCP JWT TTL (seconds)')}</Typography.Text>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            {t(
              'Lifetime for Focal AI MCP auth tokens. Range %s–%s seconds. Default %s.',
              MIN_MCP_JWT_TTL_SECONDS,
              MAX_MCP_JWT_TTL_SECONDS,
              DEFAULT_MCP_JWT_TTL_SECONDS,
            )}
          </Typography.Paragraph>
          <InputNumber
            min={MIN_MCP_JWT_TTL_SECONDS}
            max={MAX_MCP_JWT_TTL_SECONDS}
            precision={0}
            value={mcpJwtTtl}
            disabled={loading}
            style={{ width: '100%' }}
            onChange={value => {
              if (typeof value === 'number') {
                setMcpJwtTtl(value);
              }
            }}
          />
        </FieldRow>

        <ButtonRow>
          <Button
            type="primary"
            onClick={handleSaveKnown}
            loading={savingKnown}
            disabled={loading}
          >
            {t('Save')}
          </Button>
        </ButtonRow>

        <SectionTitle level={5}>{t('Free-form entries')}</SectionTitle>

        <FieldRow>
          <Input
            placeholder={t('Key')}
            value={newKey}
            disabled={loading}
            onChange={event => setNewKey(event.target.value)}
          />
          <Input
            placeholder={t('Value')}
            value={newValue}
            disabled={loading}
            onChange={event => setNewValue(event.target.value)}
          />
        </FieldRow>

        <ButtonRow>
          <Button onClick={handleAddEntry} loading={addingEntry} disabled={loading}>
            {t('Add')}
          </Button>
        </ButtonRow>

        <RowList>
          {rows.map(row => (
            <RowItem key={row.key}>
              <RowKeyValue>
                <Typography.Text strong>{row.key}</Typography.Text>
                <Typography.Paragraph
                  type="secondary"
                  style={{ marginBottom: 0 }}
                  ellipsis
                >
                  {row.value}
                </Typography.Paragraph>
              </RowKeyValue>
              <Button
                danger
                onClick={() => handleDeleteEntry(row.key)}
                loading={deletingKey === row.key}
                disabled={loading}
              >
                {t('Delete')}
              </Button>
            </RowItem>
          ))}
          {!loading && rows.length === 0 && (
            <Typography.Text type="secondary">
              {t('No stored entries.')}
            </Typography.Text>
          )}
        </RowList>
      </StyledContent>
    </>
  );
}
