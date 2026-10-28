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
import { styled } from '@apache-superset/core/theme';
import { t } from '@apache-superset/core/translation';
import { Button } from '@superset-ui/core/components';
import { Artifact, PresentedDeliverable } from '../runtime';
import { groupDeliverables } from '../deliverables';

const Results = styled.div`
  margin: 16px 0;
  overflow-wrap: anywhere;
  h4 {
    margin: 0 0 8px;
  }
  ul {
    list-style: none;
    padding: 0;
    margin: 0 0 12px;
  }
  li {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 4px 0;
  }
  .deliverable-title {
    flex: 1;
    min-width: 0;
  }
  summary {
    cursor: pointer;
  }
  .work-artifacts {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
  }
  .work-artifacts > .superset-button {
    margin: 0;
    max-width: 100%;
    height: auto;
    white-space: normal;
    text-align: start;
  }
`;

export default function DeliverableLinks({
  artifacts,
  onInspect,
  onView = onInspect,
  presentations,
}: {
  artifacts: Artifact[];
  onInspect: (id: string) => void;
  onView?: (id: string) => void;
  presentations?: PresentedDeliverable[];
}) {
  const grouped = groupDeliverables(artifacts);
  const explicit = (presentations ?? []).flatMap(entry => {
    const artifact =
      artifacts.find(item => item.id === entry.artifact_id) ??
      grouped.deliverables.find(item => item.key === entry.key)?.artifact;
    return artifact
      ? [{ key: entry.key, artifact, title: entry.title, url: undefined }]
      : [];
  });
  const deliverables =
    presentations === undefined ? grouped.deliverables : explicit;
  const selected = new Set(deliverables.map(item => item.artifact.id));
  const details = [
    ...new Map(
      [
        ...grouped.details,
        ...grouped.deliverables.map(item => item.artifact),
      ].map(item => [item.id, item]),
    ).values(),
  ].filter(item => !selected.has(item.id));
  if (!artifacts.length) return null;
  return (
    <Results>
      {deliverables.length > 0 && (
        <section aria-label={t('Deliverables')}>
          <h4>{t('Deliverables')}</h4>
          <ul>
            {deliverables.map(({ key, artifact, title }) => (
              <li key={key}>
                <a
                  className="deliverable-title"
                  href="#ai-chat-deliverables"
                  onClick={event => {
                    event.preventDefault();
                    onView(artifact.id);
                  }}
                >
                  {title}
                </a>
                <Button
                  buttonStyle="link"
                  size="small"
                  aria-label={t('View %s', title)}
                  onClick={() => onView(artifact.id)}
                >
                  {t('View')}
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {details.length > 0 && (
        <details>
          <summary>{t('Work details (%s)', details.length)}</summary>
          <div className="work-artifacts">
            {details.map(artifact => (
              <Button
                key={artifact.id}
                buttonStyle="secondary"
                onClick={() => onInspect(artifact.id)}
              >
                {t('Inspect %s', artifact.title)}
              </Button>
            ))}
          </div>
        </details>
      )}
    </Results>
  );
}
