---
title: SDK-native AI Chat architecture
sidebar_position: 10
---

<!--
Licensed to the Apache Software Foundation (ASF) under one
or more contributor license agreements. See the NOTICE file
distributed with this work for additional information
regarding copyright ownership. The ASF licenses this file
to you under the Apache License, Version 2.0 (the
"License"); you may not use this file except in compliance
with the License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied. See the License for the
specific language governing permissions and limitations
under the License.
-->

# SDK-native AI Chat architecture

## Decision and scope

The SDK-native implementation is the sole supported execution path. The
[runtime reference](ai-chat-runtime.md#execution-adapters) describes its contracts.
The conversation reset deliberately discards pre-cutover history; it does not
import legacy transcripts or checkpoints.

`engine.py` is a thin entrypoint for `native_engine.py`, which uses public SDK
FunctionTools, Runner streaming and RunState approvals. `native_session.py`
implements encrypted Session storage on SQLAlchemy 1.4. `native_model.py` uses the
SDK Chat Completions model and pinned OpenAI client, with final wire-budget,
private-image and provider-field guards. Inference has no legacy engine fallback.
The retained custom HTTP utility is used for connection verification only.

`model_settings.py` owns administrator-editable token budgets per catalogue model
identity (connection plus model). The additive `f7a8b9c0d1e2` migration imports
operator Python profiles once. `model_catalog.resolve()` supplies database values
to `store.submit()`, which freezes the effective budgets with each accepted turn.
Workers, SDK model settings and input filters consume that snapshot, so edits take
effect on new turns without changing an interrupted run. See the
[budget policy](ai-chat-runtime.md#context-budgeting-and-compaction) for validation,
reset semantics and provider-capacity limits.

`native_approvals.py` binds decisions to exact proposals; `native_context.py`
builds disposable bounded model views; `native_summarization.py` adds durable
semantic working summaries through the public async model-input filter; `native_history.py` copies complete
prefixes and seals terminal orphan calls with known or explicitly unknown results.
`runner.py` retains leases, operation records and ordered UI delivery. These are
domain extensions around Runner, not a second model/tool loop. Structured preview
references are validated before publication so missing fields become correctable
tool errors. SDK items are the only model history; UI projections remain separate.

The additive `d5e6f7a8b9c0` migration creates SDK session tables. Native contract 3
rejects older active contracts. Conversation reset is an explicit offline CLI
operation in `reset.py`, never an automatic migration side effect. The CLI checks
an exact inventory, unknown inbound foreign keys and protected-data fingerprints.
The [README](../../../README.md#sdk-native-runtime-and-conversation-reset) owns
operator commands and backup/rollback instructions.

[Hardening](../../../tests/ai_runtime/test_native_hardening.py),
[context](../../../tests/ai_runtime/test_native_context.py),
[summarization](../../../tests/ai_runtime/test_native_summarization.py),
[history](../../../tests/ai_runtime/test_native_history.py),
[store](../../../tests/ai_runtime/test_store.py) and
[reset](../../../tests/ai_runtime/test_reset.py) tests cover SDK interruptions,
transaction boundaries and scoped mutations. Retired legacy/bridge-loop tests
are replaced by native SDK contracts; shared policy, provider-verification and
BI product tests remain. Deterministic tests do not promise exactly-once remote
writes or replace process-kill/load and broader staging checks before wider rollout.

Use the Python OpenAI Agents SDK as the only agent loop. Use the OpenAI Python
client for model transport. Preserve the Chat UI and BI integration through
explicit adapters. Existing AI conversation history is disposable: do not build
legacy transcript/checkpoint import or retain a second execution engine after
cutover. Native datasets, saved charts, dashboards, provider connections, private
MCP accounts and administrator policies are outside the conversation reset.

The external Superset MCP server remains unchanged. Its separately protected
code, configuration, dependencies and deployment are outside this migration.

## Ownership and request path

```text
React Chat -> authenticated API -> queued turn / worker lease
  -> Runner.run_streamed(Agent, new input, session=FocalSession)
  -> SDK loads session and builds model input
  -> context policy -> provider adapter -> AsyncOpenAI -> model
  -> SDK FunctionTool -> authorized operation wrapper -> MCP
  -> SDK items / state -> session, events and BI artifacts
  -> persisted event cursor -> React Chat and chart pane
```

| Owner | Responsibilities |
| --- | --- |
| Agents SDK | Loop, function-tool orchestration, run items, sessions interface, approvals, run-state serialization, lifecycle hooks. |
| OpenAI Python client | HTTP requests, typed responses, standard streaming and transport errors. |
| Context extension | Model-input selection, full-request budget, evidence references and compaction. |
| Provider extension | Capability settings, required protocol fields, images and model-specific conversion. |
| BI extension | Native authorization, unchanged MCP schemas, artifact extraction and chart lineage. |
| Execution extension | Queue/lease, idempotency, effect outcomes, ordered events and safe recovery. |

SDK orchestration must invoke real function tools and consume their real bounded
results. Remove the `LedgerModel` pattern that ignores SDK input and returns
placeholder evidence acknowledgments. No application model/tool loop may run
underneath Runner.

## Dependencies and deployment

Use [the existing exact dependency pins](../../../requirements/ai-agents.txt) as
the Stage 2 baseline: `openai-agents==0.10.5`, `openai==2.19.0`, and
`pydantic==2.12.3`. This is a known project baseline, not a claim that these are
the newest releases. Retain Python 3.10 compatibility and the deployed MCP client
contract. Verify a clean dependency resolution and imports in the actual worker;
if the native integration needs an SDK fix, update pins and this decision together
before relying on that feature. Never copy SDK internals into application code.

Keep Flask, Celery, Redis, Alembic and Superset's SQLAlchemy 1.4. Do not introduce
a new workflow service, vector database, frontend framework or ORM upgrade for
this migration. The pinned SDK's bundled SQLAlchemy session imports
`async_sessionmaker`, which is incompatible with Superset's `<2` SQLAlchemy
constraint. Implement the public Session protocol with the existing ORM instead.
Do not install the SDK SQLAlchemy extra into Superset to resolve that mismatch.

SDK dependencies become required for Chat at cutover; Chat worker startup must
fail clearly on an incompatible dependency set. No silent legacy fallback.
Install, test and rollout commands belong in the
[README](../../../README.md#optional-agents-sdk-execution).

## One conversation store

`FocalSession` implements `get_items`, `add_items`, `pop_item` and `clear_session`.
It uses fresh, migration-managed tables in Superset's metadata database, encrypted
with the application's established encryption facilities. It is the sole
conversation item store; there is no second legacy message history or SDK scratch
transcript. SDK input contains only the new user turn, never a replay of already
loaded session history. Do not also enable server-managed conversation IDs or
previous-response chaining for these sessions.

The storage contract separates these records:

- Thread: UUID, owner/post, title/pin and ordered conversation revision.
- Session items: SDK-compatible JSON, stable sequence, turn association and
  encrypted provider extensions; no parallel Chat Completions transcript.
- Turns: accepted input, provider/model/config snapshot, execution version,
  lease, status and encrypted resumable SDK state.
- Operations: tool call identity, argument/schema fingerprint, approval binding,
  dispatch status and exact outcome or unknown-outcome marker.
- Events/artifacts: ordered UI projections and exact BI references; these are
  not another source of conversation history.

Names above describe responsibilities, not finalized SQL table names. A database
unique constraint enforces one active turn per thread. Session mutations require
the expected conversation revision and valid lease; process-local SDK locks are
insufficient across workers. Persist SDK appends idempotently by turn and item
position, including interrupted/resumed runs. Repeated identical user text remains
a distinct message. Do not deduplicate messages by content hash.

Pending user input belongs to the accepted turn until SDK persistence commits it;
render it from that turn without inserting it twice. Branch/retry/edit operates
on complete exchanges at an explicit revision, creates an independent session,
and preserves product semantics. A branch omits invalidated approval/run state.
Historical image and artifact references must remain authorized and usable.

## Context extension

Use the public `call_model_input_filter` as the model-view boundary. Start from
SDK-prepared history, not a separately reconstructed ledger. Verify the pinned
SDK's persistence behavior: filtering must not unintentionally erase full stored
history. Store compacted working-memory references explicitly; do not assume that
an input filter supplies durable compaction.

1. Resolve verified model/server capacity; configuration does not enlarge the
   inference server. Budget instructions, schemas, images and protocol fields as
   well as text, reserving output capacity and a conservative estimation margin.
2. Prefer the focused, authorized tool set before a round. Keep names and schemas
   stable where possible. A model adapter checks the final serialized request,
   since the history filter alone cannot account for every wire-format field.
3. Bound tool results and provide scoped evidence retrieval for omitted content.
4. Remove or summarize older complete exchanges as pressure increases. Preserve
   required instructions, the current request, unresolved calls and provider-
   required fields for every retained exchange. Never orphan call/result pairs.
5. Retrieve exact chart/evidence references when needed; summaries cannot grant
   permission or substitute for exact write arguments.
6. If mandatory content alone cannot fit, preserve the accepted input and return
   a recoverable needs-input state with a concrete remedy. Do not loop forever
   or present ordinary conversation growth as a terminal failed turn.

Use durable semantic working summaries before deterministic bounded excerpts and
whole-exchange trimming. The [runtime policy](ai-chat-runtime.md#context-budgeting-and-compaction)
defines thresholds, encrypted checkpoints, failure handling and provider-neutral
summary calls. Summarization adapts OpenAI's cookbook; it is not an SDK guarantee. On a recognized
provider context-length rejection, allow at most one tighter model-only retry;
never replay completed tools as part of that retry. Session item-count limits
alone do not implement this policy. KV-cache reuse remains an inference-server
optimization; the client does not promise cache hits.

## Provider extension

Start with Chat Completions for DeepSeek and GPUStack using `AsyncOpenAI` and
the SDK's public model interface. Prefer `OpenAIChatCompletionsModel` where it
preserves all required fields. If it does not, a narrow Model adapter may convert
requests/responses through the OpenAI client; it must consume SDK-provided input
and must not implement another agent loop or raw HTTP/SSE parser.

Capability mapping is per connection/model revision, never inferred solely from
a display name. Preserve tool-call IDs, fragmented arguments, reasoning protocol
fields, usage and finish reasons across streaming, persistence and resume.
DeepSeek requires `reasoning_content` replay for tool-bearing requests under its
documented thinking protocol. Keep such fields encrypted and out of default
logs/traces; display only content permitted by provider and administrator policy.
Compaction must respect the requirements of the retained exchanges.

Use verified model IDs and parameters from the model catalogue. OpenAI-specific
hosted tools, compaction items and conversation state are not the portable
baseline. Changing provider/model starts a compatible new run with validated
history; never resume provider-specific opaque state on another provider.

## BI, approvals and execution extensions

Wrap MCP tools as SDK FunctionTools around one reviewed invocation boundary.
Keep external schemas unchanged (`strict_json_schema=False` where necessary),
validate original arguments and recheck current user/post permissions immediately
before dispatch. SDK approval interruption handles the pause, while Focal binds
the decision to connection revision, schema, user/post, tool and exact arguments.
Expired approval cannot authorize a changed invocation.

Retain bounded concurrent reads and sequential writes through a shared scheduler.
SDK tool callbacks cannot bypass it. Questions and expired connections release the
worker; persist the corresponding interaction plus SDK state and resume the same
turn without submitting the original input again. Clarification is not approval.

Before an effect, commit its operation identity and dispatch intent. Reuse a
recorded completed outcome after recovery. An unknown write outcome becomes
`needs_review`, never an automatic retry. There is no exactly-once guarantee for
an arbitrary remote MCP tool. If SDK state cannot be safely restored after a
crash, stop for review instead of regenerating writes with new call IDs. Reads
may restart only under an explicit bounded policy.

Use public SDK state serialization for interruptions and checkpoints at safe
boundaries; do not access private Runner fields. Stage 3 must prove which pinned
streaming/state boundaries are resumable. Persist events before broadcasting;
browser reconnect reads committed sequence cursors without resubmitting work.
Cancellation stops future dispatch but cannot undo a committed operation.

Keep exact chart form data, source request, artifact IDs and version lineage.
Map SDK events into the existing frontend contract in
`superset-frontend/src/features/ai/runtime.ts`; retain `RuntimeWorkspace`,
`ChatChartEmbed`, composer and activity/action components. One translator emits
text/tool/status events; do not emit both raw provider and SDK text as replies.
Tracing stays disabled until a deliberate redaction/export configuration exists.

## Replacement map

| Existing area | Target action |
| --- | --- |
| `engine.py`, `native_engine.py`, `execution.py` | SDK-native orchestration and one execution contract; bridge removed. |
| `native_model.py`, `providers.py` | SDK model transport; retain custom HTTP utility only for connection verification. |
| `native_context.py`, `context.py`, `evidence.py` | SDK input filtering and bounded retrieval; legacy projections/discovery loop removed. |
| `store.py`, runtime/message models | Fresh Session storage and thread/product operations; no legacy history import. |
| `runner.py`, `worker.py`, `notifications.py` | Retain/simplify delivery, lease, operation recovery and committed event replay. |
| `policy.py`, `tool_access.py`, `connections.py`, `mcp.py` | Retain domain policy/security; use SDK tool/MCP mechanisms where compatible. |
| `artifacts.py`, `artifact_memory.py`, `images.py` | Preserve product contracts, scopes and exact references; adapt to session items. |
| Model catalogue, settings, workflows and React UI | Preserve product behavior; remove obsolete engine selection only at cutover. |

## Stage gates and cutover

| Stage | Required evidence before advancing |
| --- | --- |
| 1: architecture | Explicit ownership, dependency decision, single history path, context/recovery contracts and scoped reset plan. |
| 2: native vertical slice | Clean worker dependency check; SDK input reaches captured wire payload; session round trip without duplicates; DeepSeek thinking on/off with repeated tools; GPUStack tool/stream compatibility; create and modify an unsaved chart, verify right pane after reload. |
| 3: hardening | Long-history trimming and oversized-input recovery; schema-heavy request; interrupted stream; approval reject/change/revoke; clarification and connection repair resume; cancellation; duplicate delivery; worker death before/after effect and session append; branch/edit/retry; scoped images/evidence and ordered SSE reconnect. |
| 4: cutover | Scoped reset dry run and backup reviewed; staging checks pass on both providers; no legacy code/config/history reader remains; full product regression passes on fresh sessions. |

Stage 2 is an isolated validation path, not another permanent production engine.
Implement one provider/session slice before migrating the remaining surfaces.
Run unit/contract checks before live provider checks and browser checks. Record
actual sent payloads in redacted test assertions; successful final answers alone
do not prove context safety or recovery. Existing tests are a behavioral baseline,
not evidence that the replacement already passes.

At Stage 4, stop submissions, quiesce workers and settle pending/unknown writes.
Inventory explicit AI-owned tables, attached files and shared-table foreign keys;
dry-run exact row/file counts before any deletion. Reset only conversation-owned
history, state, evidence, previews and unreferenced private images. Preserve saved
BI resources, connections, credentials and policy settings. Do not truncate the
metadata database. Old conversation URLs return a clear reset/not-found state.
Retain the pre-cutover code/database backup for restore, not a live legacy path;
restore must reconcile remote effects rather than rerun old jobs blindly.

## Sources and verification limits

The design follows OpenAI's public [SDK ownership guidance](https://developers.openai.com/api/docs/guides/agents/sdk),
[sessions and streaming](https://developers.openai.com/api/docs/guides/agents/running-agents),
[run state](https://developers.openai.com/api/docs/guides/agents/results), and
[DeepSeek thinking requirements](https://api-docs.deepseek.com/guides/thinking_mode/).
Public documentation may describe later releases. The pinned Session protocol,
input-filter hook and SQLAlchemy backend imports were inspected locally for this
decision. [Native contract tests](../../../tests/ai_runtime/test_native_sdk.py)
check actual Runner input, fragmented calls, DeepSeek replay, session scope and
idempotent appends, filtering without stored-history loss, and rejection before
transport when the final request exceeds its estimated budget. The
[live evaluation](../../../tests/ai_runtime/live_sdk_evaluation.py) checks real
providers and chart-edit invariants, plus unchanged connection settings and saved
resource counts. Additional Stage 3 tests above exercise approval boundaries, interrupted callbacks
and scoped mutations. Full cutover remains subject to the Stage 4 gates.


## Visual deliverables

The Chat application owns presentation through `ai_runtime/deliverables.py`.
Saved chart/dashboard results register automatically; `present_deliverable` is a
Chat-only SDK helper for completed previews and result tables. It validates scoped
artifact references and successful source execution, then appends an idempotent,
encrypted presentation entry to the existing ledger. It does not mutate artifacts,
change BI permissions or introduce a second agent loop. Session/turn projections and
streaming events feed a single-view Deliverables panel, with diagnostic evidence in
a separate Details drawer. See the [runtime policy](./ai-chat-runtime.md#session-deliverables-viewer)
for rendering, authorization, legacy-session and branch behavior.
