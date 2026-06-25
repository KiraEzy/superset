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
import {
  rewriteChartExploreUrl,
  rewriteSupersetExploreUrl,
} from './supersetUrlUtils';

describe('rewriteSupersetExploreUrl', () => {
  const originalOrigin = window.location.origin;

  beforeEach(() => {
    Object.defineProperty(window, 'location', {
      value: { origin: 'http://192.168.11.122:9000' },
      writable: true,
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      value: { origin: originalOrigin },
      writable: true,
    });
  });

  test('rewrites relative explore URLs', () => {
    expect(rewriteSupersetExploreUrl('/explore/?slice_id=42')).toBe(
      'http://192.168.11.122:9000/explore/?slice_id=42',
    );
  });

  test('rewrites localhost absolute URLs', () => {
    expect(
      rewriteSupersetExploreUrl('http://localhost:9000/explore/?slice_id=42'),
    ).toBe('http://192.168.11.122:9000/explore/?slice_id=42');
  });

  test('rewrites scheme-less localhost explore URLs', () => {
    expect(
      rewriteSupersetExploreUrl('localhost:9000/explore/?slice_id=42'),
    ).toBe('http://192.168.11.122:9000/explore/?slice_id=42');
  });

  test('leaves external URLs unchanged', () => {
    const url = 'https://example.com/explore/?slice_id=42';
    expect(rewriteSupersetExploreUrl(url)).toBe(url);
  });
});

describe('rewriteChartExploreUrl', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'location', {
      value: { origin: 'http://192.168.11.122:9000' },
      writable: true,
    });
  });

  test('rewrites chart explore_url', () => {
    const chart = rewriteChartExploreUrl({
      id: 'chart-0',
      viz_type: 'pie',
      form_data: { viz_type: 'pie' },
      explore_url: 'http://localhost:9000/explore/?slice_id=42',
    });
    expect(chart.explore_url).toBe(
      'http://192.168.11.122:9000/explore/?slice_id=42',
    );
  });
});
