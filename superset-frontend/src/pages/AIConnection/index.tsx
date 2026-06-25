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
import { useEffect, useRef, useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { styled, css } from '@apache-superset/core/theme';
import { Alert } from '@apache-superset/core/components';
import {
  Button,
  Form,
  Input,
  InputNumber,
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
  DEFAULT_AI_CONNECTION_CONFIG,
  getAiConnectionConfig,
  LlmProvider,
  saveAiConnectionConfig,
  stashProviderLlmSettings,
  switchAiConnectionProvider,
} from 'src/features/ai/aiConnectionConfig';
import {
  testLlmConnection,
  testMcpConnection,
} from 'src/features/ai/aiChatApi';

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

export default function AIConnection() {
  const [form] = Form.useForm<AiConnectionConfig>();
  const { addSuccessToast, addDangerToast } = useToasts();
  const [testingMcp, setTestingMcp] = useState(false);
  const [testingLlm, setTestingLlm] = useState(false);
  const [saving, setSaving] = useState(false);
  const activeProviderRef = useRef<LlmProvider>(
    DEFAULT_AI_CONNECTION_CONFIG.llmProvider,
  );
  const [providerKey, setProviderKey] = useState(0);

  const readLlmFields = (): {
    llmApiBaseUrl: string;
    llmModel: string;
    llmApiKey: string;
  } => ({
    llmApiBaseUrl: String(form.getFieldValue('llmApiBaseUrl') ?? ''),
    llmModel: String(form.getFieldValue('llmModel') ?? ''),
    llmApiKey: String(form.getFieldValue('llmApiKey') ?? ''),
  });

  const applyLlmFields = (config: Pick<
    AiConnectionConfig,
    'llmProvider' | 'llmApiBaseUrl' | 'llmModel' | 'llmApiKey'
  >) => {
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
    stashProviderLlmSettings(activeProviderRef.current, readLlmFields());
  };

  useEffect(() => {
    const config = getAiConnectionConfig();
    form.setFieldsValue(config);
    activeProviderRef.current = config.llmProvider;
  }, [form]);

  const menuData: SubMenuProps = {
    name: t('AI Connection'),
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      const values = await form.validateFields();
      saveAiConnectionConfig(values);
      addSuccessToast(t('AI connection settings saved.'));
    } catch {
      addDangerToast(t('Please fix the form errors before saving.'));
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
        'llmApiBaseUrl',
        'llmApiKey',
        'llmModel',
      ]);
      const result = await testLlmConnection(values);
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

  const handleReset = () => {
    form.setFieldsValue({ ...DEFAULT_AI_CONNECTION_CONFIG });
  };

  return (
    <>
      <SubMenu {...menuData} />
      <StyledContent>
        <Typography.Paragraph type="secondary">
          {t(
            'Configure the LLM provider (Gemini, DeepSeek, LM Studio, OpenAI, etc.) and Superset MCP. Chat requests run through the Superset backend with full MCP tool calling.',
          )}
        </Typography.Paragraph>

        <Form form={form} layout="vertical" initialValues={DEFAULT_AI_CONNECTION_CONFIG}>
          <SectionTitle level={5}>{t('LLM Provider')}</SectionTitle>

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
                const fromProvider = activeProviderRef.current;
                const nextConfig = switchAiConnectionProvider(
                  fromProvider,
                  readLlmFields(),
                  value,
                );
                applyLlmFields(nextConfig);
              }}
            />
          </Form.Item>

          <Form.Item
            name="llmApiBaseUrl"
            label={t('API base URL')}
            rules={[{ required: true, message: t('API base URL is required') }]}
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
            extra={t('Example: gemini-2.0-flash, deepseek-chat, or your LM Studio model id')}
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
            extra={t('Required for Gemini, DeepSeek, and OpenAI. Optional for LM Studio.')}
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
          </ButtonRow>

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
            rules={[{ required: true, message: t('MCP server URL is required') }]}
            extra={t('Example: http://localhost:5008/mcp')}
          >
            <Input placeholder="http://localhost:5008/mcp" />
          </Form.Item>

          <Form.Item
            name="mcpBearerToken"
            label={t('MCP bearer token')}
            extra={t('Required only when MCP JWT authentication is enabled')}
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
            name="agentMaxIterations"
            label={t('Max tool iterations')}
            rules={[
              { required: true, message: t('Max tool iterations is required') },
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
            message={t('Settings are stored in this browser')}
            description={t(
              'LLM settings are remembered per provider in this browser. MCP settings are shared. You do not need to click Save when switching providers.',
            )}
            style={{ marginTop: 24 }}
          />

          <ButtonRow>
            <Button type="primary" onClick={handleSave} loading={saving}>
              {t('Save')}
            </Button>
            <Button onClick={handleReset}>{t('Reset to defaults')}</Button>
          </ButtonRow>
        </Form>
      </StyledContent>
    </>
  );
}
