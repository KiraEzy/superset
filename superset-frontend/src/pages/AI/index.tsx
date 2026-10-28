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
import { useState, useEffect } from 'react';
import { t } from '@apache-superset/core/translation';
import { Loading } from '@superset-ui/core/components';
import { Alert } from '@apache-superset/core/components';
import RuntimeWorkspace from 'src/features/ai/components/RuntimeWorkspace';
import { runtimeGet, RuntimeMetadata } from 'src/features/ai/runtime';

export default function AI() {
  const [runtime, setRuntime] = useState<RuntimeMetadata | null>(null);
  const [checked, setChecked] = useState(false);
  const [runtimeError, setRuntimeError] = useState(false);
  useEffect(() => {
    let mounted = true;
    runtimeGet<RuntimeMetadata>('runtime/')
      .then(metadata => {
        if (mounted) setRuntime(metadata);
      })
      .catch(() => {
        if (mounted) setRuntimeError(true);
      })
      .finally(() => {
        if (mounted) setChecked(true);
      });
    return () => {
      mounted = false;
    };
  }, []);
  if (!checked) return <Loading />;
  if (runtimeError)
    return (
      <Alert
        type="error"
        message={t(
          'Chat could not load. Check your connection and active post, then refresh.',
        )}
      />
    );
  return runtime?.enabled ? (
    <RuntimeWorkspace metadata={runtime} />
  ) : (
    <Alert type="info" message={t('AI Chat is temporarily unavailable.')} />
  );
}
