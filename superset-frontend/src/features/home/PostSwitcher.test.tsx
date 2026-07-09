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
import { render, screen } from 'spec/helpers/testing-library';
import PostSwitcher from './PostSwitcher';

const viewer = { id: 1, name: 'viewer', label: 'Viewer' };
const editor = { id: 2, name: 'editor', label: 'Editor' };

test('renders greeting with first and last name and post label for a single post', () => {
  render(
    <PostSwitcher
      firstName="Ada"
      lastName="Lovelace"
      username="ada"
      activePost={viewer}
      availablePosts={[viewer]}
    />,
  );

  expect(
    screen.getByText('Hi, Ada Lovelace, you are logged in as,'),
  ).toBeInTheDocument();
  expect(screen.getByText('Viewer')).toBeInTheDocument();
  expect(screen.queryByTestId('post-switcher')).not.toBeInTheDocument();
});

test('falls back to username when first and last name are empty', () => {
  render(
    <PostSwitcher
      firstName="  "
      lastName=""
      username="ada"
      activePost={viewer}
      availablePosts={[viewer]}
    />,
  );

  expect(
    screen.getByText('Hi, ada, you are logged in as,'),
  ).toBeInTheDocument();
});

test('shows dropdown when multiple posts are available', () => {
  render(
    <PostSwitcher
      firstName="Ada"
      lastName="Lovelace"
      username="ada"
      activePost={viewer}
      availablePosts={[viewer, editor]}
    />,
  );

  expect(screen.getByTestId('post-switcher')).toBeInTheDocument();
  expect(screen.getByText('Viewer')).toBeInTheDocument();
  expect(
    screen.getByText('Hi, Ada Lovelace, you are logged in as,'),
  ).toBeInTheDocument();
});

test('still renders greeting when there are zero available posts', () => {
  render(
    <PostSwitcher
      firstName="Ada"
      lastName="Lovelace"
      username="ada"
      activePost={null}
      availablePosts={[]}
    />,
  );

  expect(
    screen.getByText('Hi, Ada Lovelace, you are logged in as,'),
  ).toBeInTheDocument();
  expect(screen.getByText('Choose post')).toBeInTheDocument();
});

test('exposes full display name via tooltip title for truncation', () => {
  const longFirst = 'A'.repeat(40);
  const longLast = 'B'.repeat(40);
  render(
    <PostSwitcher
      firstName={longFirst}
      lastName={longLast}
      username="ada"
      activePost={viewer}
      availablePosts={[viewer]}
    />,
  );

  const fullName = `${longFirst} ${longLast}`;
  expect(screen.getByTitle(fullName)).toBeInTheDocument();
});
