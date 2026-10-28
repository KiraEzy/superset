# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.
# Chat-only image; external MCP server is outside this build.
FROM apachesuperset.docker.scarf.sh/apache/superset@sha256:5822dff49c41fd745ce33e38af502f9c64df30d133aeba148c5d89b35a1004ef
USER root
COPY requirements/ai-chat.txt requirements/ai-agents.txt /tmp/focal-ai-requirements/
RUN uv venv --python /app/.venv/bin/python /opt/focal-ai \
    && /opt/focal-ai/bin/python -c "import site; from pathlib import Path; Path(site.getsitepackages()[0], 'application.pth').write_text('/app/.venv/lib/python3.10/site-packages\n')" \
    && uv pip install --python /opt/focal-ai/bin/python -r /tmp/focal-ai-requirements/ai-chat.txt -r /tmp/focal-ai-requirements/ai-agents.txt \
    && uv pip check --python /opt/focal-ai/bin/python
