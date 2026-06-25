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
import { AiChatChartPayload } from './types';

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '0.0.0.0']);

const SCHEMELESS_LOCAL_EXPLORE_RE =
  /^(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?(\/explore\/.*)$/i;

/** Whether a URL should be rewritten to the browser's current origin. */
export function shouldRewriteSupersetUrl(url: string): boolean {
  if (!url?.trim()) {
    return false;
  }
  const trimmed = url.trim();
  if (trimmed.startsWith('/explore/')) {
    return true;
  }
  if (SCHEMELESS_LOCAL_EXPLORE_RE.test(trimmed)) {
    return true;
  }
  try {
    const parsed = new URL(trimmed);
    return (
      LOCAL_HOSTS.has(parsed.hostname) ||
      (parsed.pathname.includes('/explore/') && LOCAL_HOSTS.has(parsed.hostname))
    );
  } catch {
    return false;
  }
}

/** Rewrite localhost or relative Superset URLs to the browser's current origin. */
export function rewriteSupersetExploreUrl(url: string): string {
  if (!url?.trim()) {
    return url;
  }
  const trimmed = url.trim();
  const origin = window.location.origin;
  if (trimmed.startsWith('/')) {
    return `${origin}${trimmed}`;
  }
  const schemelessMatch = trimmed.match(SCHEMELESS_LOCAL_EXPLORE_RE);
  if (schemelessMatch) {
    return `${origin}${schemelessMatch[3]}`;
  }
  try {
    const parsed = new URL(trimmed);
    if (LOCAL_HOSTS.has(parsed.hostname)) {
      return `${origin}${parsed.pathname}${parsed.search}${parsed.hash}`;
    }
  } catch {
    // not a valid absolute URL — return as-is
  }
  return trimmed;
}

export function rewriteChartExploreUrl(
  chart: AiChatChartPayload,
): AiChatChartPayload {
  if (!chart.explore_url) {
    return chart;
  }
  return {
    ...chart,
    explore_url: rewriteSupersetExploreUrl(chart.explore_url),
  };
}
