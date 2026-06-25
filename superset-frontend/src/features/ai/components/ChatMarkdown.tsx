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
import { useMemo, useState, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { styled, css, useTheme } from '@apache-superset/core/theme';
import { t } from '@apache-superset/core/translation';
import { Icons } from '@superset-ui/core/components/Icons';
import {
  rewriteSupersetExploreUrl,
  shouldRewriteSupersetUrl,
} from 'src/features/ai/supersetUrlUtils';

const MarkdownWrapper = styled.div`
  ${({ theme }) => css`
    line-height: 1.7;
    word-break: break-word;

    > *:first-child {
      margin-top: 0;
    }
    > *:last-child {
      margin-bottom: 0;
    }

    p {
      margin: 0 0 ${theme.sizeUnit * 2}px;
      &:last-child {
        margin-bottom: 0;
      }
    }

    strong {
      font-weight: 600;
    }

    em {
      font-style: italic;
    }

    a {
      color: ${theme.colorPrimary};
      text-decoration: none;
      &:hover {
        text-decoration: underline;
      }
    }

    h1, h2, h3, h4, h5, h6 {
      margin: ${theme.sizeUnit * 3}px 0 ${theme.sizeUnit * 1.5}px;
      font-weight: 600;
      line-height: 1.3;
      &:first-child {
        margin-top: 0;
      }
    }
    h1 { font-size: 1.4em; }
    h2 { font-size: 1.25em; }
    h3 { font-size: 1.1em; }
    h4, h5, h6 { font-size: 1em; }

    ul, ol {
      margin: 0 0 ${theme.sizeUnit * 2}px;
      padding-left: ${theme.sizeUnit * 5}px;
    }
    li {
      margin-bottom: ${theme.sizeUnit}px;
      &:last-child {
        margin-bottom: 0;
      }
    }
    li > p {
      margin-bottom: ${theme.sizeUnit}px;
    }

    blockquote {
      margin: 0 0 ${theme.sizeUnit * 2}px;
      padding: ${theme.sizeUnit}px ${theme.sizeUnit * 3}px;
      border-left: 3px solid ${theme.colorPrimary};
      background: ${theme.colorBgTextHover};
      border-radius: 0 ${theme.borderRadius}px ${theme.borderRadius}px 0;
      color: ${theme.colorTextSecondary};
      > p:last-child {
        margin-bottom: 0;
      }
    }

    hr {
      border: none;
      border-top: 1px solid ${theme.colorBorderSecondary};
      margin: ${theme.sizeUnit * 3}px 0;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      margin: 0 0 ${theme.sizeUnit * 2}px;
      font-size: ${theme.fontSizeSM}px;
    }
    thead {
      background: ${theme.colorBgTextHover};
    }
    th {
      text-align: left;
      font-weight: 600;
      padding: ${theme.sizeUnit * 1.5}px ${theme.sizeUnit * 2}px;
      border-bottom: 2px solid ${theme.colorBorderSecondary};
    }
    td {
      padding: ${theme.sizeUnit * 1.5}px ${theme.sizeUnit * 2}px;
      border-bottom: 1px solid ${theme.colorBorderSecondary};
    }
    tr:last-child td {
      border-bottom: none;
    }

    img {
      max-width: 100%;
      border-radius: ${theme.borderRadius}px;
    }
  `}
`;

const CodeBlock = styled.div`
  ${({ theme }) => css`
    position: relative;
    margin: 0 0 ${theme.sizeUnit * 2}px;
    border-radius: ${theme.borderRadiusLG}px;
    overflow: hidden;
    background: ${theme.colorBgLayout};
    border: 1px solid ${theme.colorBorderSecondary};
  `}
`;

const CodeBlockHeader = styled.div`
  ${({ theme }) => css`
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: ${theme.sizeUnit}px ${theme.sizeUnit * 2.5}px;
    background: ${theme.colorBgTextHover};
    border-bottom: 1px solid ${theme.colorBorderSecondary};
    font-size: ${theme.fontSizeSM - 1}px;
    color: ${theme.colorTextSecondary};
  `}
`;

const CopyButton = styled.button`
  ${({ theme }) => css`
    display: flex;
    align-items: center;
    gap: ${theme.sizeUnit}px;
    border: none;
    background: none;
    color: ${theme.colorTextSecondary};
    font-size: ${theme.fontSizeSM - 1}px;
    cursor: pointer;
    padding: 2px 6px;
    border-radius: ${theme.borderRadius}px;
    transition: all 0.15s;
    &:hover {
      background: ${theme.colorBgContainer};
      color: ${theme.colorText};
    }
  `}
`;

const CodeContent = styled.pre`
  ${({ theme }) => css`
    margin: 0;
    padding: ${theme.sizeUnit * 2.5}px;
    overflow-x: auto;
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: ${theme.fontSizeSM}px;
    line-height: 1.5;
    color: ${theme.colorText};
    code {
      font-family: inherit;
      background: none;
      padding: 0;
      border-radius: 0;
      font-size: inherit;
    }
  `}
`;

const InlineCode = styled.code`
  ${({ theme }) => css`
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 0.88em;
    padding: 1px 5px;
    background: ${theme.colorBgTextHover};
    border: 1px solid ${theme.colorBorderSecondary};
    border-radius: ${theme.borderRadius}px;
    color: ${theme.colorErrorText};
  `}
`;

const ChartLink = styled.a`
  ${({ theme }) => css`
    display: inline-flex;
    align-items: center;
    gap: ${theme.sizeUnit}px;
    padding: ${theme.sizeUnit * 1.5}px ${theme.sizeUnit * 2.5}px;
    border-radius: ${theme.borderRadiusLG}px;
    background: ${theme.colorPrimaryBg};
    color: ${theme.colorPrimary};
    font-weight: 500;
    font-size: ${theme.fontSizeSM}px;
    text-decoration: none;
    border: 1px solid ${theme.colorPrimaryBorder};
    transition: all 0.2s;
    &:hover {
      background: ${theme.colorPrimaryBgHover};
      text-decoration: none;
    }
  `}
`;

const ToolsUsedBar = styled.div`
  ${({ theme }) => css`
    display: flex;
    flex-wrap: wrap;
    gap: ${theme.sizeUnit}px;
    padding-top: ${theme.sizeUnit * 2}px;
    margin-top: ${theme.sizeUnit * 2}px;
    border-top: 1px solid ${theme.colorBorderSecondary};
  `}
`;

const ToolBadge = styled.span`
  ${({ theme }) => css`
    display: inline-flex;
    align-items: center;
    gap: ${theme.sizeUnit * 0.5}px;
    padding: 2px ${theme.sizeUnit * 1.5}px;
    font-size: ${theme.fontSizeSM - 1}px;
    background: ${theme.colorBgTextHover};
    color: ${theme.colorTextSecondary};
    border-radius: ${theme.borderRadius}px;
    border: 1px solid ${theme.colorBorderSecondary};
  `}
`;

const CHART_LINK_RE = /\[([^\]]*)\]\((https?:\/\/[^\s)]*\/explore\/\?slice_id=(\d+)[^\s)]*)\)/g;
const TOOLS_USED_RE = /\n\n—\n_Tools used: (.+)_$/;

function CodeBlockRenderer({
  language,
  children,
}: {
  language: string;
  children: string;
}) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(children).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [children]);

  return (
    <CodeBlock>
      <CodeBlockHeader>
        <span>{language || 'text'}</span>
        <CopyButton onClick={handleCopy}>
          {copied ? (
            <>
              <Icons.CheckOutlined iconSize="xs" />
              {t('Copied')}
            </>
          ) : (
            <>
              <Icons.CopyOutlined iconSize="xs" />
              {t('Copy')}
            </>
          )}
        </CopyButton>
      </CodeBlockHeader>
      <CodeContent>
        <code>{children}</code>
      </CodeContent>
    </CodeBlock>
  );
}

interface ChatMarkdownProps {
  content: string;
}

export default function ChatMarkdown({ content }: ChatMarkdownProps) {
  const theme = useTheme();

  const { body, toolsUsed } = useMemo(() => {
    const match = content.match(TOOLS_USED_RE);
    if (match) {
      return {
        body: content.slice(0, match.index),
        toolsUsed: match[1].split(', ').map(s => s.trim()).filter(Boolean),
      };
    }
    return { body: content, toolsUsed: [] as string[] };
  }, [content]);

  const processedBody = useMemo(
    () =>
      body.replace(CHART_LINK_RE, (_match, label, url, sliceId) => {
        const safeLabel = label || `Chart ${sliceId}`;
        const rewrittenUrl = rewriteSupersetExploreUrl(url);
        return `[📊 ${safeLabel}](${rewrittenUrl})`;
      }),
    [body],
  );

  const remarkPlugins = useMemo(() => [remarkGfm], []);

  const components = useMemo(
    () => ({
      code({
        inline,
        className,
        children: codeChildren,
        ...props
      }: {
        inline?: boolean;
        className?: string;
        children?: React.ReactNode;
      }) {
        const lang = className?.replace('language-', '') ?? '';
        const codeText = String(codeChildren).replace(/\n$/, '');
        if (inline) {
          return <InlineCode {...props}>{codeChildren}</InlineCode>;
        }
        return <CodeBlockRenderer language={lang}>{codeText}</CodeBlockRenderer>;
      },
      a({
        href,
        children: linkChildren,
        ...props
      }: {
        href?: string;
        children?: React.ReactNode;
      }) {
        const resolvedHref =
          href && shouldRewriteSupersetUrl(href)
            ? rewriteSupersetExploreUrl(href)
            : href;
        const isChartLink =
          resolvedHref && /\/explore\/\?slice_id=\d+/.test(resolvedHref);
        if (isChartLink) {
          return (
            <ChartLink
              href={resolvedHref}
              target="_blank"
              rel="noopener noreferrer"
              {...props}
            >
              {linkChildren}
            </ChartLink>
          );
        }
        return (
          <a
            href={resolvedHref}
            target="_blank"
            rel="noopener noreferrer"
            {...props}
          >
            {linkChildren}
          </a>
        );
      },
    }),
    [],
  );

  return (
    <MarkdownWrapper>
      <ReactMarkdown remarkPlugins={remarkPlugins} components={components}>
        {processedBody}
      </ReactMarkdown>
      {toolsUsed.length > 0 && (
        <ToolsUsedBar>
          <span
            style={{
              fontSize: theme.fontSizeSM - 1,
              color: theme.colorTextSecondary,
              fontWeight: 500,
            }}
          >
            {t('Tools used')}:
          </span>
          {toolsUsed.map(tool => (
            <ToolBadge key={tool}>{tool}</ToolBadge>
          ))}
        </ToolsUsedBar>
      )}
    </MarkdownWrapper>
  );
}
