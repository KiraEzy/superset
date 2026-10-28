/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership. The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License. You may obtain a copy of the License at
 * http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { Alert } from '@apache-superset/core/components';
import {
  Button,
  Form,
  InputNumber,
  Modal,
  Typography,
} from '@superset-ui/core/components';
import {
  CatalogModel,
  catalogRequest,
  ModelTokenLimits,
} from '../modelCatalog';

export default function ModelSettingsModal({
  model,
  onHide,
  onSaved,
}: {
  model: CatalogModel;
  onHide: () => void;
  onSaved: () => Promise<void>;
}) {
  const settings = model.runtime_settings!;
  const [values, setValues] = useState<
    Record<keyof ModelTokenLimits, number | null>
  >(settings.values);
  const [reset, setReset] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const allowance =
    (values.context_window_tokens ?? 0) -
    (values.response_tokens ?? 0) -
    (values.tool_result_tokens ?? 0);
  const valid =
    Object.values(values).every(
      value =>
        value !== null &&
        Number.isInteger(value) &&
        value >= 1 &&
        value <= 100000000,
    ) && allowance >= 1024;
  const fields: { key: keyof ModelTokenLimits; label: string; hint: string }[] =
    [
      {
        key: 'context_window_tokens',
        label: t('Context window (tokens)'),
        hint: t(
          'Set this to the context capacity configured on your model server.',
        ),
      },
      {
        key: 'response_tokens',
        label: t('Maximum response tokens'),
        hint: t('Reserved for the model’s reply.'),
      },
      {
        key: 'tool_result_tokens',
        label: t('Tool-result reservation (tokens)'),
        hint: t('Reserved for results returned by tools.'),
      },
    ];
  const save = async () => {
    if (!valid) return;
    setSaving(true);
    setError('');
    try {
      await catalogRequest(`${model.id}/settings`, {
        revision: settings.revision,
        ...(reset ? { reset: true } : { values }),
      });
      await onSaved();
      onHide();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : t('Could not save model settings.'),
      );
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal
      show
      centered
      width={520}
      title={t('Model settings')}
      onHide={() => {
        if (!saving) onHide();
      }}
      maskClosable={false}
      footer={
        <div css={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Button
            buttonStyle="link"
            disabled={saving}
            css={{ marginRight: 'auto' }}
            onClick={() => {
              setValues(settings.defaults);
              setReset(true);
              setError('');
            }}
          >
            {t('Restore defaults')}
          </Button>
          <Button buttonStyle="secondary" disabled={saving} onClick={onHide}>
            {t('Cancel')}
          </Button>
          <Button
            buttonStyle="primary"
            loading={saving}
            disabled={!valid}
            onClick={save}
          >
            {t('Save model settings')}
          </Button>
        </div>
      }
    >
      <Typography.Paragraph>
        <strong>{model.name}</strong>
        <br />
        <Typography.Text type="secondary">{model.connection}</Typography.Text>
      </Typography.Paragraph>
      {error && (
        <Alert showIcon closable={false} type="error" message={error} />
      )}
      <Form layout="vertical">
        {fields.map(field => (
          <Form.Item
            key={field.key}
            label={field.label}
            htmlFor={`model-${field.key}`}
            extra={field.hint}
          >
            <InputNumber
              id={`model-${field.key}`}
              aria-label={field.label}
              value={values[field.key]}
              min={1}
              max={100000000}
              step={1}
              disabled={saving}
              style={{ width: '100%' }}
              onChange={value => {
                setValues(previous => ({ ...previous, [field.key]: value }));
                setReset(false);
              }}
            />
          </Form.Item>
        ))}
      </Form>
      <Alert
        closable={false}
        type={valid ? 'info' : 'error'}
        message={
          valid
            ? t('Input allowance: %s tokens', allowance.toLocaleString())
            : t(
                'Leave at least 1,024 input tokens after reserving response and tool-result capacity.',
              )
        }
        description={t(
          'Instructions, tool schemas and safety margins also use this space.',
        )}
      />
      <Typography.Paragraph
        type="secondary"
        css={{ marginTop: 16, marginBottom: 0 }}
      >
        {t(
          'Applies to new turns for this connection and model. Running turns keep their existing settings.',
        )}
      </Typography.Paragraph>
    </Modal>
  );
}
