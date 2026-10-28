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
import { useCallback, useEffect, useRef, useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { styled, css } from '@apache-superset/core/theme';
import { SupersetClient } from '@superset-ui/core';
import ModelCatalogue from 'src/features/ai/components/ModelCatalogue';
import {
  catalogRequest,
  waitVerification,
  ModelCatalogue as Catalogue,
} from 'src/features/ai/modelCatalog';
import { Alert } from '@apache-superset/core/components';
import {
  Button,
  Form,
  Input,
  InputNumber,
  Loading,
  Select,
  Switch,
  Typography,
} from '@superset-ui/core/components';
import SubMenu, { SubMenuProps } from 'src/features/home/SubMenu';
import { useToasts } from 'src/components/MessageToasts/withToasts';
import {
  AGENT_MAX_ITERATIONS_MAX,
  AGENT_MAX_ITERATIONS_MIN,
  AiConnectionConfig,
  buildConfigFromState,
  DEFAULT_AI_CONNECTION_CONFIG,
  fetchAiConnectionState,
  getDefaultProviderLlmSettings,
  LlmProvider,
  mergeConfigIntoState,
  ProviderLlmSettings,
  saveAiConnectionState,
  StoredAiConnectionState,
} from 'src/features/ai/aiConnectionConfig';
import {
  testLlmConnection,
  testMcpConnection,
} from 'src/features/ai/aiChatApi';
import McpToolAccessEditor from 'src/features/ai/components/McpToolAccessEditor';

const StyledContent = styled.div`
  ${({ theme }) => css`
    width: min(1840px, calc(100% - 24px));
    display: grid;
    grid-template-columns: minmax(360px, 680px) minmax(420px, 1fr);
    gap: 24px;
    align-items: start;
    @media (max-width: 1100px) {
      grid-template-columns: minmax(0, 1fr);
    }
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
    flex-wrap: wrap;
    gap: ${theme.sizeUnit * 2}px;
    margin-top: ${theme.sizeUnit * 4}px;
  `}
`;

export default function AIConnection() {
  const [form] = Form.useForm<AiConnectionConfig>();
  const { addSuccessToast, addDangerToast } = useToasts();
  const [testingMcp, setTestingMcp] = useState(false);
  const [testingLlm, setTestingLlm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const activeProviderRef = useRef<LlmProvider>(
    DEFAULT_AI_CONNECTION_CONFIG.llmProvider,
  );
  // In-memory source of truth for per-provider drafts and shared settings.
  const stateRef = useRef<StoredAiConnectionState>({
    llmProvider: DEFAULT_AI_CONNECTION_CONFIG.llmProvider,
    providerSettings: {},
    mcpEnabled: DEFAULT_AI_CONNECTION_CONFIG.mcpEnabled,
    mcpServerUrl: DEFAULT_AI_CONNECTION_CONFIG.mcpServerUrl,
    mcpBearerToken: DEFAULT_AI_CONNECTION_CONFIG.mcpBearerToken,
    agentMaxIterations: DEFAULT_AI_CONNECTION_CONFIG.agentMaxIterations,
    systemPrompt: DEFAULT_AI_CONNECTION_CONFIG.systemPrompt,
  });
  const providerDraftsRef = useRef<
    Partial<Record<LlmProvider, ProviderLlmSettings>>
  >({});
  const [providerKey, setProviderKey] = useState(0);
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [connectionId, setConnectionId] = useState('');
  const [connectionName, setConnectionName] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [savingReasoning, setSavingReasoning] = useState(false);
  const [verifyStatus, setVerifyStatus] = useState('');
  const initializedConnection = useRef(false);
  const reloadCatalogue = useCallback(async () => {
    const data = await catalogRequest<Catalogue>();
    if (!initializedConnection.current) {
      const active = data.models.find(m => m.default);
      const connection = data.connections.find(
        c => c.id === active?.connection_id,
      );
      if (connection) {
        initializedConnection.current = true;
        setConnectionId(connection.id);
        setConnectionName(connection.label);
        form.setFieldsValue(connection.config);
        activeProviderRef.current = connection.config.llmProvider;
      }
    }
    setCatalogue(data);
  }, [form]);
  useEffect(() => {
    reloadCatalogue().catch(() =>
      addDangerToast(t('Could not load model catalogue.')),
    );
  }, [reloadCatalogue, addDangerToast]);

  const readLlmFields = (): ProviderLlmSettings => ({
    llmApiBaseUrl: String(form.getFieldValue('llmApiBaseUrl') ?? ''),
    llmModel: String(form.getFieldValue('llmModel') ?? ''),
    llmApiKey: String(form.getFieldValue('llmApiKey') ?? ''),
  });

  const applyLlmFields = (
    config: Pick<
      AiConnectionConfig,
      'llmProvider' | 'llmApiBaseUrl' | 'llmModel' | 'llmApiKey'
    >,
  ) => {
    form.setFieldsValue({
      llmProvider: config.llmProvider,
      llmApiBaseUrl: config.llmApiBaseUrl,
      llmModel: config.llmModel,
      llmApiKey: config.llmApiKey,
    });
    activeProviderRef.current = config.llmProvider;
    setProviderKey(prev => prev + 1);
  };

  const persistActiveProviderDraft = () => {
    providerDraftsRef.current[activeProviderRef.current] = readLlmFields();
  };

  useEffect(() => {
    let cancelled = false;
    fetchAiConnectionState()
      .then(state => {
        if (cancelled) {
          return;
        }
        stateRef.current = state;
        providerDraftsRef.current = { ...state.providerSettings };
        const fields = buildConfigFromState(state);
        if (initializedConnection.current) {
          form.setFieldsValue({
            mcpEnabled: fields.mcpEnabled,
            mcpServerUrl: fields.mcpServerUrl,
            mcpBearerToken: fields.mcpBearerToken,
            mcpToolAccess: fields.mcpToolAccess,
            agentMaxIterations: fields.agentMaxIterations,
            systemPrompt: fields.systemPrompt,
          });
        } else {
          form.setFieldsValue(fields);
          activeProviderRef.current = state.llmProvider;
        }
        setLoaded(true);
      })
      .catch(() => {
        if (cancelled) return;
        setLoadFailed(true);
        addDangerToast(t('Failed to load AI connection settings.'));
      });
    return () => {
      cancelled = true;
    };
  }, [form, addDangerToast]);

  const menuData: SubMenuProps = {
    name: t('AI Connection'),
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      const values = await form.validateFields([
        'mcpEnabled',
        'mcpServerUrl',
        'mcpBearerToken',
        'mcpToolAccess',
        'agentMaxIterations',
        'systemPrompt',
      ]);
      // Model connections are saved independently through verification.
      const existing = buildConfigFromState(stateRef.current);
      stateRef.current = mergeConfigIntoState(stateRef.current, {
        ...values,
        llmProvider: existing.llmProvider,
        llmApiBaseUrl: existing.llmApiBaseUrl,
        llmApiKey: existing.llmApiKey,
        llmModel: existing.llmModel,
        llmAdapter: existing.llmAdapter,
      });
      const saved = await saveAiConnectionState(stateRef.current);
      stateRef.current = saved;

      addSuccessToast(t('AI connection settings saved.'));
    } catch (error) {
      addDangerToast(
        error instanceof Error && error.message
          ? error.message
          : t('Please fix the form errors before saving.'),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleTestMcp = async () => {
    try {
      setTestingMcp(true);
      const values = await form.validateFields([
        'mcpServerUrl',
        'mcpBearerToken',
      ]);
      const result = await testMcpConnection(values);
      if (result.ok) {
        addSuccessToast(result.message);
      } else {
        addDangerToast(result.message);
      }
    } catch {
      addDangerToast(t('Please enter a valid MCP server URL.'));
    } finally {
      setTestingMcp(false);
    }
  };

  const handleTestLlm = async () => {
    try {
      setTestingLlm(true);
      const values = await form.validateFields([
        'llmProvider',
        'llmApiBaseUrl',
        'llmApiKey',
        'llmModel',
      ]);
      const result = await testLlmConnection({
        ...values,
        llmConnectionId: connectionId,
      });
      if (result.ok) {
        addSuccessToast(result.message);
      } else {
        addDangerToast(result.message);
      }
    } catch {
      addDangerToast(t('Please enter a valid LLM API base URL.'));
    } finally {
      setTestingLlm(false);
    }
  };

  const handleSaveReasoning = async () => {
    setSavingReasoning(true);
    try {
      await catalogRequest(`connections/${connectionId}/reasoning-visibility`, {
        showModelReasoning: form.getFieldValue('showModelReasoning') === true,
      });
      await reloadCatalogue();
      addSuccessToast(t('Reasoning display saved. Applies to new turns.'));
    } catch (error) {
      addDangerToast(
        error instanceof Error
          ? error.message
          : t('Could not save reasoning display.'),
      );
    } finally {
      setSavingReasoning(false);
    }
  };

  const handleVerify = async () => {
    setVerifying(true);
    try {
      await form.validateFields(['llmProvider', 'llmApiBaseUrl', 'llmModel']);
      const job = await catalogRequest<{ id: string }>('connections/verify', {
        ...(connectionId ? { id: connectionId } : {}),
        label: connectionName,
        config: {
          ...readLlmFields(),
          llmProvider: form.getFieldValue('llmProvider'),
          llmAdapter: form.getFieldValue('llmAdapter') || 'chat_completions',
          showModelReasoning: form.getFieldValue('showModelReasoning') === true,
        },
      });
      const verifiedConnectionId = await waitVerification(
        job.id,
        setVerifyStatus,
      );
      await reloadCatalogue();
      setConnectionId(verifiedConnectionId);
      addSuccessToast(t('Connection verified and saved.'));
    } catch (error) {
      addDangerToast(
        error instanceof Error
          ? error.message
          : t('Connection verification failed.'),
      );
    } finally {
      setVerifying(false);
    }
  };

  const handleReset = () => {
    form.setFieldsValue({ ...DEFAULT_AI_CONNECTION_CONFIG });
  };

  return (
    <>
      <SubMenu {...menuData} />
      <StyledContent>
        {!loaded &&
          (loadFailed ? (
            <Alert
              type="error"
              message={t(
                'Saved settings could not load. Reload this page before making changes.',
              )}
            />
          ) : (
            <Loading />
          ))}
        <div hidden={!loaded}>
          <Typography.Paragraph type="secondary">
            {t(
              'Manage named model connections and the shared MCP server. Publish models in the panel on the right; existing user permissions remain enforced.',
            )}
          </Typography.Paragraph>

          <Form
            form={form}
            layout="vertical"
            initialValues={DEFAULT_AI_CONNECTION_CONFIG}
          >
            <SectionTitle level={5}>{t('LLM connections')}</SectionTitle>
            <label>{t('Saved connection')}</label>
            <Select
              ariaLabel={t('Saved connection')}
              disabled={verifying}
              value={connectionId}
              css={{ width: '100%', marginBottom: 12 }}
              options={[
                { value: '', label: t('Add a connection') },
                ...(catalogue?.connections.map(c => ({
                  value: c.id,
                  label: c.label,
                })) ?? []),
              ]}
              onChange={value => {
                const id = String(value);
                setConnectionId(id);
                setVerifyStatus('');
                const connection = catalogue?.connections.find(
                  c => c.id === id,
                );
                setConnectionName(connection?.label ?? '');
                if (connection) {
                  applyLlmFields(connection.config);
                  form.setFieldValue(
                    'showModelReasoning',
                    connection.config.showModelReasoning === true,
                  );
                  form.setFieldValue(
                    'llmAdapter',
                    connection.config.llmAdapter,
                  );
                } else {
                  form.setFieldsValue({
                    llmApiKey: '',
                    llmModel: '',
                    llmApiBaseUrl: '',
                    llmAdapter: 'chat_completions',
                    showModelReasoning: false,
                  });
                }
              }}
            />
            <label htmlFor="model-connection-name">
              {t('Connection name')}
            </label>
            <Input
              id="model-connection-name"
              aria-label={t('Connection name')}
              maxLength={128}
              value={connectionName}
              onChange={e => setConnectionName(e.target.value)}
              style={{ marginBottom: 16 }}
            />
            {connectionId && (
              <Button
                danger
                disabled={verifying}
                onClick={async () => {
                  if (
                    !window.confirm(
                      t(
                        'Delete this model connection? Existing conversation history and accepted turns remain.',
                      ),
                    )
                  )
                    return;
                  try {
                    await SupersetClient.delete({
                      endpoint: `/api/v1/ai_connection/models/connections/${connectionId}`,
                    });
                    setConnectionId('');
                    setConnectionName('');
                    await reloadCatalogue();
                  } catch {
                    addDangerToast(
                      t(
                        'Could not delete connection. Publish another default first if this connection supplies it.',
                      ),
                    );
                  }
                }}
              >
                {t('Delete connection')}
              </Button>
            )}

            <Form.Item
              name="llmProvider"
              label={t('Provider')}
              rules={[{ required: true, message: t('Provider is required') }]}
            >
              <Select
                options={[
                  { label: 'Google Gemini', value: 'gemini' },
                  { label: 'DeepSeek', value: 'deepseek' },
                  { label: 'LM Studio', value: 'lmstudio' },
                  { label: 'OpenAI', value: 'openai' },
                  { label: t('Custom (OpenAI-compatible)'), value: 'custom' },
                ]}
                onChange={(value: LlmProvider) => {
                  if (value === activeProviderRef.current) {
                    return;
                  }
                  // Remember the current provider's draft in memory.
                  providerDraftsRef.current[activeProviderRef.current] =
                    readLlmFields();

                  const llm =
                    providerDraftsRef.current[value] ??
                    getDefaultProviderLlmSettings(value);
                  applyLlmFields({ llmProvider: value, ...llm });
                  if (value !== 'openai')
                    form.setFieldValue('llmAdapter', 'chat_completions');
                  form.setFieldValue('showModelReasoning', false);
                }}
              />
            </Form.Item>

            <Form.Item
              name="llmApiBaseUrl"
              label={t('API base URL')}
              rules={[
                { required: true, message: t('API base URL is required') },
              ]}
              extra={t(
                'Gemini: https://generativelanguage.googleapis.com/v1beta/openai — LM Studio: http://localhost:1234/v1',
              )}
            >
              <Input
                placeholder="http://localhost:1234/v1"
                onBlur={persistActiveProviderDraft}
              />
            </Form.Item>

            <Form.Item
              name="llmModel"
              label={t('Model')}
              rules={[{ required: true, message: t('Model is required') }]}
              extra={t(
                'Example: gemini-2.0-flash, deepseek-chat, or your LM Studio model id',
              )}
            >
              <Input
                placeholder="e.g. qwen2.5-7b-instruct"
                onBlur={persistActiveProviderDraft}
              />
            </Form.Item>

            <Form.Item
              key={`llm-api-key-${providerKey}`}
              name="llmApiKey"
              label={t('API key')}
              extra={t(
                'Required for Gemini, DeepSeek, and OpenAI. Optional for LM Studio.',
              )}
            >
              <Input.Password
                placeholder={t('Optional')}
                autoComplete="off"
                onBlur={persistActiveProviderDraft}
              />
            </Form.Item>

            <ButtonRow>
              <Button onClick={handleTestLlm} loading={testingLlm}>
                {t('Test LLM connection')}
              </Button>
              <Button
                type="primary"
                onClick={handleVerify}
                loading={verifying}
                disabled={!connectionName.trim()}
              >
                {t('Verify and save connection')}
              </Button>
            </ButtonRow>
            {verifyStatus && <p role="status">{verifyStatus}</p>}
            <Form.Item
              name="llmAdapter"
              label={t('Model API protocol')}
              extra={t(
                'OpenAI Responses applies only to the OpenAI provider. Other providers use compatible Chat Completions.',
              )}
            >
              <Select
                options={[
                  { value: 'chat_completions', label: t('Chat Completions') },
                  { value: 'responses', label: t('OpenAI Responses') },
                ]}
              />
            </Form.Item>

            <Form.Item
              noStyle
              shouldUpdate={(previous, next) =>
                previous.llmProvider !== next.llmProvider
              }
            >
              {({ getFieldValue }) =>
                ['custom', 'lmstudio', 'deepseek'].includes(
                  getFieldValue('llmProvider'),
                ) ? (
                  <>
                    <Form.Item
                      name="showModelReasoning"
                      label={t('Show model reasoning to users')}
                      valuePropName="checked"
                      extra={t(
                        'Displays this model’s streamed reasoning in chat. It can include sensitive context. Applies to new turns and does not enable thinking.',
                      )}
                    >
                      <Switch />
                    </Form.Item>
                    {connectionId && (
                      <Button
                        loading={savingReasoning}
                        disabled={verifying}
                        onClick={handleSaveReasoning}
                      >
                        {t('Save reasoning display')}
                      </Button>
                    )}
                  </>
                ) : null
              }
            </Form.Item>

            <SectionTitle level={5}>{t('Superset MCP')}</SectionTitle>

            <Form.Item
              name="mcpEnabled"
              label={t('Enable MCP')}
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>

            <Form.Item
              name="mcpServerUrl"
              label={t('MCP server URL')}
              rules={[
                { required: true, message: t('MCP server URL is required') },
              ]}
              extra={t('Example: http://localhost:5008/mcp')}
            >
              <Input placeholder="http://localhost:5008/mcp" />
            </Form.Item>

            <Form.Item
              name="mcpBearerToken"
              label={t('MCP bearer token')}
              extra={t(
                'Focal BI supplies user/post authentication automatically when enabled. Leave blank unless this deployment requires a separate service token.',
              )}
            >
              <Input.Password placeholder={t('Optional')} autoComplete="off" />
            </Form.Item>

            <ButtonRow>
              <Button onClick={handleTestMcp} loading={testingMcp}>
                {t('Test MCP connection')}
              </Button>
            </ButtonRow>

            <SectionTitle level={5}>{t('Agent')}</SectionTitle>
            <Form.Item
              name="mcpToolAccess"
              label={t('MCP tool access by role and user')}
            >
              <McpToolAccessEditor />
            </Form.Item>

            <Form.Item
              name="agentMaxIterations"
              label={t('Max tool iterations')}
              rules={[
                {
                  required: true,
                  message: t('Max tool iterations is required'),
                },
                {
                  type: 'number',
                  min: AGENT_MAX_ITERATIONS_MIN,
                  max: AGENT_MAX_ITERATIONS_MAX,
                  message: t(
                    'Enter a value between %s and %s',
                    AGENT_MAX_ITERATIONS_MIN,
                    AGENT_MAX_ITERATIONS_MAX,
                  ),
                },
              ]}
              extra={t(
                'Maximum LLM ↔ MCP tool rounds per chat message. Default is 120.',
              )}
            >
              <InputNumber
                min={AGENT_MAX_ITERATIONS_MIN}
                max={AGENT_MAX_ITERATIONS_MAX}
                precision={0}
                style={{ width: '100%' }}
              />
            </Form.Item>

            <Form.Item
              name="systemPrompt"
              label={t('System prompt')}
              extra={t(
                'Optional instructions prepended to every chat. Leave empty to use the server default.',
              )}
            >
              <Input.TextArea
                rows={6}
                placeholder={t('Use server default system prompt')}
              />
            </Form.Item>

            <Alert
              type="info"
              showIcon
              message={t('Settings are shared across all users')}
              description={t(
                'Only administrators manage connections. Verify and save LLM connections separately, publish user model availability on the right, and save shared MCP and agent settings below.',
              )}
              style={{ marginTop: 24 }}
            />

            <ButtonRow>
              <Button type="primary" onClick={handleSave} loading={saving}>
                {t('Save MCP and agent settings')}
              </Button>
              <Button onClick={handleReset}>{t('Reset to defaults')}</Button>
            </ButtonRow>
          </Form>
        </div>
        {catalogue && (
          <ModelCatalogue data={catalogue} reload={reloadCatalogue} />
        )}
      </StyledContent>
    </>
  );
}
