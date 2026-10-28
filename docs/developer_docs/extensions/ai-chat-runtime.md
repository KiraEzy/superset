---
title: Durable AI Chat runtime
hide_title: true
sidebar_position: 9
---

# Durable AI Chat runtime

For the planned replacement, see the
[SDK-native architecture and migration gates](ai-sdk-architecture.md). That design
permits resetting disposable AI history and removes the legacy execution path at
cutover; the implementation described below remains the deployed baseline until
the replacement passes its validation gates.

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

The Chat client treats the existing Superset MCP server as an external dependency.
Its tools, authentication, schemas, middleware, deployment and dependencies are
unchanged. Resolve compatibility in `superset/ai_runtime/mcp.py`. A necessary
server change requires the owner's separate, explicit approval with evidence,
alternatives, proposed diff, client impact, verification and rollback.

## Execution and storage

`superset/ai_runtime/api.py` authenticates each request and binds a conversation
to its creator and active post. Session UUIDs remain public thread identifiers.
The browser submits intent and selected resource references, never authoritative
history or credentials. Native permissions validate referenced BI resources.
An unavailable conversation returns 403/404 without disclosing another post's
history. The Chat client opens a clean workspace for the active post instead of
retaining a stale conversation URL after a post switch.

Submission atomically commits a user message, a queued turn and an outbox record.
A unique active key allows one nonterminal turn per thread; the idempotency key
returns the original turn only when its submitted payload matches. The dedicated
AI worker dispatches the outbox and obtains a database lease before execution.

The metadata database owns encrypted checkpoints, tool outcomes, ordered events,
artifacts and pending interactions. SSE reads committed events using a sequence
cursor; native Last-Event-ID takes precedence over the original URL cursor when
reconnecting, and reconnecting does not resubmit work. Redis pub/sub provides best-effort
wakeups with database polling as the fallback. Redis/Celery is delivery
infrastructure, not the record of execution. Text events are batched at 150 ms
boundaries. Completed outcomes are reused after recovery. An interrupted write
with an unknown outcome enters `needs_review`; inspect its target before cancelling
the turn and starting a new branch. Cancellation never reverses committed effects.

Active execution defaults to 120 model rounds, 120 tool calls and 20 minutes.
Agent questions checkpoint and release the worker. Supported MCP form elicitation
retains a live connection for at most five minutes. Up to four reviewed reads
may run concurrently; writes run sequentially. Transient model requests retry at
most twice before visible output; read transports retry twice; uncertain writes
never retry automatically.

An expired or rejected MCP connection pauses the same turn for administrator
repair in AI Connection. Users choose Resume after administrator repair. Waiting for
input does not consume the active execution budget. Tool argument errors are
returned to the model for at most two corrections without dispatching an action.

## Execution adapters

The `sdk_native` path uses Runner streaming, public SDK approval state and
Session storage directly. Its execution contract is version 3. Encrypted
`ai_sdk_session` and `ai_sdk_item` tables hold the sole model history; legacy UI
messages are not inference input. Model and MCP connection settings are preserved.
The SDK is the sole supported engine. Pre-cutover chat history is reset rather
than imported; old conversation URLs return not found.

Native tools pause at a durable SDK approval checkpoint before dispatch. Reads
are authorized automatically, with up to four concurrent reads; writes are
exclusive and require existing application policy/approval. Exact call IDs,
arguments, schema hashes and scoped bindings are rechecked on resume. Completed
outcomes are reused. Unknown write outcomes require review, never automatic replay.
Clarification and connection repair resume the checkpoint. Accepted steering
rejects undispatched proposals and queues a focused continuation. Cancellation
stops future dispatch but cannot undo remote effects.

The native model view omits old complete exchanges/tool batches while retaining
pending call/result structure and required instructions. Storage stays intact;
bounded evidence references support retrieval. Oversized irreducible input pauses
for a shorter focused request. One recognized context-length rejection may retry
before visible output; unrelated provider errors do not. Estimates are conservative
heuristics, not exact provider token counts. Durable semantic summaries supplement
this filtering; neither mechanism enlarges a provider's physical context window.

Private image IDs are scoped at submission and hydrated only at the wire boundary
for image-verified models. Provider reasoning remains encrypted; gradual display
requires the existing explicit custom/LM Studio opt-in. Fork/edit/retry copy only
complete SDK prefixes and clear inherited approvals. Recovery replaces partial
browser text using ordered `message_reset` events. Local chart previews validate
structured column/metric references against the authorized datasource and return
correctable tool errors for missing references; SQL expressions still require
normal Superset query validation. See the [architecture and gates](ai-sdk-architecture.md).

`settings.execution_snapshot()` always accepts native contract 3 with the pinned
SDK version. The former execution-engine selector is ignored; client payloads
cannot select another engine. `engine.run_turn` rejects old contracts instead of
falling back. The legacy loop, bridge adapter and canonical transcript reader have
been removed. SDK Session items are the only model history. Turn/message rows
remain delivery, activity and UI projections, not another model transcript.

SDK callbacks dispatch only checkpointed call IDs through the domain policy
boundary. Original server schemas remain unchanged. Provider reasoning fields stay
in encrypted SDK items; external SDK tracing is disabled. The retained HTTP
provider utility supports connection verification, not the agent execution loop.

The AI page uses RuntimeWorkspace exclusively. Disabling Chat displays an
unavailable state and rejects submissions; it never opens the legacy composer.
Deleting a conversation also deletes its scoped SDK items. The offline reset
command deletes only an exact captured inventory of conversation tables, rejects
unexpected inbound foreign keys, and compares protected connection/BI fingerprints
before commit. Images are stored in the private image table, not external files.

Use the [README](../../../README.md#sdk-native-runtime-and-conversation-reset)
for installation, evaluation, reset and rollback commands. Rollback requires the
pre-cutover code/image and database backup with remote-effect reconciliation;
there is no runtime switch back to the retired engine.

## Canonical action policy

Application security and execution policy have highest priority, followed by
administrator BI guidance, explicit user intent and accepted steering, selected
versioned workflows, then sourced connection guidance and retrieved data. Tool
results cannot grant permissions or approve actions.

Exploration previews charts. Direct, bounded save/edit instructions can execute
within their target scope; ambiguous targets require a question or confirmation.
In the default Ask for approval mode, destructive, access-changing and
unclassified operations require approval.
Approvals bind the connection/version, user/post, schema, tool and normalized
arguments. Batched calls retain each exact approval or decline across sequential
user responses before the SDK dispatches the batch; answering a later call does
not reopen an unchanged earlier decision. Changing any bound value invalidates
approval. Existing Superset permissions still authorize the actual tool invocation.
Third-party annotations
are preserved metadata; administrators classify tools independently. SQL execution
is unclassified because even apparently read-only SQL can have effects.

The composer also offers Full access: an explicit user choice to skip routine
Chat confirmations for tools within the user's existing Superset and MCP scope.
It never grants resource access, changes credentials, bypasses argument validation,
or retries unknown write outcomes. Identical completed writes with new call IDs
still require review; cached outcomes for the same call ID remain reusable.
The mode is stored per turn, defaults to Ask for approval, and survives recovery.
The selector can change an active turn through authenticated, scoped
`POST /api/v1/ai/turns/{id}/approval-mode`; changes are audited and reach the worker
through trusted input. Changes apply at the next approval boundary and do not
undo an operation already dispatched. Full access resumes a paused approval checkpoint, including
an expired one, by revalidating tools under the new explicit policy rather than
reusing an expired grant. Forked history resets to Ask for approval.

Expired approval buttons become Refresh approval. Refreshing grants nothing: it
queues the SDK checkpoint to validate the proposal and issue a fresh request.
Server rejection messages, including expiration, are displayed in Chat.

`policy.py` is the canonical implementation. Extend its argument-aware rules and
tests together. Never infer permission from an annotation, model-generated text
or a tool result.

`tool_access.py` applies administrator Chat restrictions in addition to native
permissions. Matching active-post role allowlists are combined; an explicit user
allowlist intersects that result. No matching rule adds no restriction. An empty
matching list denies all BI tools. Filter model-visible tools during discovery
and reload current policy before each dispatch/retry. Revocation fails before
recording an operation as dispatched, so it cannot become an uncertain write.
These restrictions never grant native MCP permissions or change server schemas.

## Context budgeting and compaction

`native_context.py` filters SDK input without rewriting stored Session items.
Whole earlier user exchanges are omitted first, then complete assistant/tool-result
batches within the active exchange. Pending call/result groups and required system
instructions stay paired and intact. Bounded omission notes retain source-request
excerpts and exact call IDs for scoped `read_evidence` retrieval; chart references
remain available through `read_artifact`. Filtering remains the fallback when
semantic summarization cannot complete; the retired canonical-message
`context_memory` pipeline is not restored.

`native_summarization.py` adapts the [OpenAI session-memory cookbook](https://developers.openai.com/cookbook/examples/agents_sdk/session_memory)
at the public asynchronous SDK model-input filter. At 70% of the available input
allowance it summarizes older completed exchanges, aiming below 50%, preferably
retaining two recent exchanges and always retaining the current request and
unresolved protocol suffix. Completed batches within a long turn can also be
summarized. Recent retained items keep original provider fields. Full SDK items,
positions, UI messages and chart artifacts are never rewritten.

The selected chat connection generates tools-disabled JSON summaries of goals,
constraints, decisions, work status, uncertainties and exact resource/evidence
references. Output is capped at 1024 tokens and reduced for smaller allowances.
Historical strings are excerpted at 6000 characters before ordered, bounded
summary requests; reasoning and image bytes are excluded. Summaries are lossy
historical data, not instructions, permissions, proof of success or write arguments.
Retrieve exact authorized evidence/configuration before acting.

The additive `e6f7a8b9c0d1` migration creates encrypted `ai_sdk_summary` checkpoints.
A checkpoint binds the covered prefix fingerprint, boundary, model binding,
owner/post and policy version. Publication checks the worker lease and session
revision. Restarts reuse valid summaries; branches regenerate from their own SDK
history. Prefix edits/truncation and binding changes invalidate reuse. Session
removal deletes its summary. No history reset or connection change is needed.

Each preparation allows at most 30 seconds, bounded by remaining turn time, with
one request per chunk and no automatic retry. A compaction failure suppresses
further compaction attempts in that run, avoiding repeated waits in tool rounds;
a new user turn can try again. Invalid JSON, timeout or provider
failure retains the last valid checkpoint and falls back to safe trimming.
Irreducible input still pauses for focused input. Diagnostics record outcome,
boundary, estimates, duration and reported token usage, never summary/history text.
This is an application adapter around the SDK, not a built-in summarization switch
or an implementation of OpenAI Responses compaction or hardened KV-cache reuse.

Tool outputs have bounded visible bodies and exact encrypted records. Evidence
retrieval rechecks current tool/schema permissions and dataset scope. Replaying a
completed call ID reuses its recorded outcome; a new read call refreshes evidence.
Every model request advertises all currently authorized external tool schemas plus
internal helpers, without a tool-count cap or discovery prerequisite.
`find_bi_tools` is an optional search aid and does not change tool availability.
Resumed runs rebuild availability from the authorized catalog instead of reusing
older selection checkpoints. All advertised schemas count toward context budgets;
authorization, exact-proposal approvals and final request-budget guards still apply.
List argument policy still caps Focal catalogue pages and reports effective args.

The final wire estimate includes serialized instructions/schemas/settings, a UTF-8
byte heuristic and 4096 tokens per image before private hydration. Output and tool
result capacity are reserved. Unknown models default to a 32768-token configured
window; verified official DeepSeek V4 endpoints use a 128000 operational cap.
Administrators configure each connection/model in **AI Connection → Available in
Chat → Settings**, using a centered dialog. Context window, maximum response
tokens and tool-result reservation are database-owned in `ai_model`; identities
with the same model name on different connections remain independent. The input
allowance is context minus response and tool reservations; instructions, schemas,
images and safety margins consume that allowance. Values must be integer tokens
from 1 through 100,000,000 and leave at least 1,024 input tokens. This validation
does not discover or enlarge the inference server's actual capacity.

Migration `f7a8b9c0d1e2` copies `AI_RUNTIME_MODEL_CONTEXT_LIMITS` into existing model
rows once, including any legacy `context_chars` override. Run it with the original
application configuration loaded before removing those Python entries; see the
[operator instructions](../../../README.md#model-context-settings). Resolved
catalogue models subsequently ignore Python profiles. New models start with
application defaults. Restore defaults clears the row's overrides (including a
migrated `context_chars` value), and only persists when Save is clicked; it does
not restore the migrated profile. Official DeepSeek endpoint defaults remain
128,000 context tokens, other models 32,768, with 4,096 each for response and tool
reservation. Explicit migrated values take precedence over those defaults.

`POST /api/v1/ai_connection/models/<model_id>/settings` requires administrator and
`AIConnectionConfig` write access, with `revision` and all three `values`, or
`reset: true`. A stale revision returns 409; malformed or unusable values return
400. Saving budgets does not reverify credentials or change publication. New
turns snapshot the effective settings and revision in their encrypted state;
queued, active and resumed turns retain their accepted budgets. These snapshots
drive SDK model settings, trimming, summarization, final wire guards and context
usage events. No process restart is required for settings edits.

SDK filtering uses a safety margin; one recognized pre-output
context rejection retries a smaller view. If required input still cannot fit, the
turn pauses for a focused request instead of failing with a context-overflow error.

Budget persistence, migration, connection isolation, stale-edit rejection and
captured SDK wire requests are covered by
[`test_model_settings.py`](../../../tests/ai_runtime/test_model_settings.py).

Saved history and exact artifacts remain available. Dropped exchanges are not
promised as remembered facts: retrieve required evidence or continue in a focused
branch. Model/token/tool/time limits still bound execution. The SDK does not
automatically infer business intent, prevent every repeated discovery call, or
make remote writes exactly-once. The retained `context.py` contains only resource
context and shared hashing/token-estimation helpers.

## Chart follow-up references

`artifact_memory.py` exposes a small chart index plus the Chat-only `read_artifact`
tool. It resolves the latest permitted chart or an exact artifact ID inside the
same conversation, user and post. Native chart/dataset access is rechecked on
retrieval. Full snapshots include form_data, preview cache key, saved/preview state,
provenance and the original MCP request config. Metadata reads of the same cached
preview can recover its originating config. These references survive refresh,
compaction and conversation branches; they do not authorize writes.

Artifact paths start at the artifact root, for example `payload.form_data`, not
the response's `data` wrapper. A path error on an authorized artifact advertises
its root keys and exact `read_artifact` examples. Unauthorized/unavailable
artifacts retain a generic error without disclosing root fields.

The agent loads the baseline before modifying a prior chart, preserves unchanged
dataset/metrics/filters, and uses the existing MCP tools for supported changes.
New previews carry a parent artifact reference and incremented version. Reading
metadata for the same unchanged preview reuses its artifact instead of creating
a duplicate or resetting its version. Chat
normalizes current text-backed/cached preview responses: the existing native
GetFormDataCommand resolves missing form_data with its access checks. This stores
a durable rendering snapshot; an expiring cache key does not erase an already
captured chart. No MCP tool, schema or endpoint is changed. Unsupported styles
must be reported rather than claimed as applied. Creating a preview never saves
or edits the source BI resource.

## Session Deliverables viewer

The right-hand **Deliverables** panel presents completed visuals from the entire
conversation through a compact picker and one selected viewer. It groups saved
resources by connection, type and resource ID, showing their latest snapshot.
The initial selection is the latest dashboard, otherwise the latest visual.
An explicit user selection stays selected as other results arrive; updated entries
are marked in the picker. Only the selected chart/table or dashboard is mounted.
A successful native dashboard rebuild with explicit `remove_chart_ids` retires those
charts from this session's presentation, including legacy history. Inspection reads
do not restore them; a later saved edit or explicit presentation can. Their saved BI
resources and evidence remain intact. Standalone charts not explicitly removed are
preserved, and equal titles never imply replacement. A full-registry SSE update
removes retired entries immediately; forked tool history and preserved artifact
timestamps retain this projection.
Inspection reads can refresh an existing result but cannot publish a new one.
Native charts reuse the existing renderer. Native dashboards use an authenticated,
same-origin `/superset/dashboard/<id>/?standalone=2` frame and an Open dashboard
link. Loading, inaccessible and timed-out frames retain that recovery action;
arbitrary HTML and external frames are unsupported.

Successful saved charts and dashboards register automatically. The Chat-only
`present_deliverable` SDK helper presents an existing completed chart preview or
table, with `artifact_id`, `title` and optional `replaces_artifact_id`. It neither
saves BI resources nor authorizes writes. Tools return exact persisted artifact
references so the model can publish a finished visual instead of a diagnostic
probe. Publication checks conversation/user/post scope, successful source execution,
current native chart/dataset/database access and a supported renderer. A replacement
must be accessible and have the same type; distinct saved resource IDs cannot merge,
and an unsaved preview cannot replace a saved resource.

Registrations append encrypted `AiRuntimeItem(kind="deliverable")` entries;
artifact snapshots remain immutable. Registration identity is deterministic for
replay safety, keyed by the SDK tool call for explicit publication. A changed replay
is rejected; a new publication call may change a title again. Session and turn
responses include additive `deliverables` metadata;
SSE `deliverable` events upsert by logical key. Reloads recheck access and show an
unavailable state for revoked results. Existing sessions derive saved-resource
entries without rewriting history. Historical previews/tables are not implicitly
published. Forks remap only registrations whose artifacts were copied to the branch.
No migration, history reset or external MCP change is required.

Chat deliverable links select the current version in the viewer. SQL, raw JSON,
standalone URLs, intermediate inspections and older snapshots remain under chat
**Work details**; Inspect opens a separate Details drawer. Raw payloads, SQL JSON
and nested JSON table values start collapsed under **Details**. Charts, ordinary
table values and resource links remain readable. Full audit history, model evidence
and permission requirements are preserved; publication is not task verification.

Verification: `tests/ai_runtime/test_deliverables.py` covers persistence, replacement,
source outcomes, access revocation and forks; the SDK contract tests exercise the
helper through the actual Runner. `DeliverablesPanel.test.tsx`, the runtime reducer
and chat-link tests cover selection, single-view loading, replay and evidence access.

## Components and contracts

- `store.py`, `models/ai_runtime.py`: scoped turn service and authoritative ledger.
- `runner.py`, `worker.py`: leases, checkpoints, dispatch, recovery and identity refresh.
- `engine.py`, `native_engine.py`: thin entrypoint and public SDK Runner orchestration.
- `native_context.py`, `context.py`: bounded SDK model views and shared resource context.
- `native_model.py`: SDK Chat Completions transport, scoped image hydration and
  provider-field/budget guards. `providers.py` remains a connection-verification
  utility; its Responses probe is not the Chat orchestration path.
  Compatible self-hosted and DeepSeek profiles may opt in to visible reasoning.
- `mcp.py`, `connections.py`: FastMCP lifecycle, typed/text-backed normalization,
  approved HTTP destinations, separate credentials and scoped discovery.
- `workflows/`: trusted, versioned instruction packages; no executable extensions.
- `RuntimeWorkspace.tsx`: history, chat, artifact inspection and mobile pane navigation.

Turn endpoints live under `/api/v1/ai/`: `threads/{uuid}/turns`,
`turns/{uuid}`, `turns/{uuid}/events`, `cancel`, `input`, and
`threads/{uuid}/fork`. Events carry schema version 1, thread/turn/item IDs,
a monotonically increasing sequence, timestamp, type and typed payload.
Forking copies completed context and artifacts without executing tools; saved BI
resources persist. `mode=after` includes the selected completed reply. The default
`before` excludes it. `mode=retry` excludes that reply and submits its persisted
prompt, context and workflows in the branch. Dispatched writes block automatic
retry, including failed or uncertain outcomes. Copied turns/messages receive
branch-local IDs so older replies can be branched again at the correct boundary.
The reply action bar uses the shared clipboard utility, including its HTTP fallback.
`work_activity` supplies active execution seconds and visible activity in turn
snapshots and assistant-message metadata. Session reads batch-load activity for
historical replies. The Worked-for disclosure precedes reply text and replaces the
separate Activity block. Reasoning-content deltas remain encrypted continuation
data. Compatible self-hosted and DeepSeek profiles can explicitly opt in to a visible copy;
otherwise their presence emits only a generic thinking status. Public provider
summaries remain distinct from that opt-in model reasoning. Forks copy visible activity without dispatching
tools. Existing records without measured duration display Work details.

Public activity streams through additive `activity_updated` events. Each contains
`payload.item` with the complete `id`, `kind`, `status` and `payload`; consumers
upsert by ID and reject stale sequence numbers. The item update and event commit
atomically. Polling and reconnect snapshots remain authoritative. Provider summary
parts have stable IDs scoped to the turn and model generation, so final summaries
replace streamed previews instead of duplicating them. Updates batch at 150 ms and
flush before phase transitions or termination. Interrupted or cancelled phases
retain that outcome rather than reporting completion.

Named `custom`/`lmstudio`/`deepseek` connections support the administrator
`showModelReasoning` preference, default false. The Chat-only administrator endpoint
`POST /api/v1/ai_connection/models/connections/{id}/reasoning-visibility` accepts
`{showModelReasoning: boolean}`. It changes only the encrypted display preference,
not credentials, model revisions or verification status; pending verification must
finish first. New turns snapshot this value. It does not backfill prior turns or
remove previously displayed text when disabled.

Compatible `reasoning` text deltas are normalized to `reasoning_content` for
encrypted continuation and use the same display opt-in and retry protection.
For opted-in compatible connections, streamed `reasoning_content` also produces
batched `model_reasoning` activity with the same generation ID. The encrypted
original stays intact for provider continuation. Visible text is safe-rendered as
Model reasoning, separate from the answer/public summary, and follows the same
ownership, post scope, replay and branching access checks. Other profiles retain
status/tool fallback. Empty thinking phases are plain status labels rather than
empty disclosures. No extra summarization call is made for reasoning display. Context memory uses
separate bounded calls as described above. Interrupted generations restore a durable SDK checkpoint or reset partial text
before safe regeneration. Unknown writes still require review.

The disclosure opens during execution and collapses on completion unless manually
toggled. The workspace preserves manual state when a live reply becomes a historical
message. Summary fragments do not trigger live announcements or force scrolling;
phase/status changes use polite announcements. Existing conversations need no backfill
or schema migration. Verify with provider/store tests and frontend runtime-reducer
and WorkActivity tests, plus desktop/mobile refresh and keyboard checks.
`mode=edit` additionally accepts a validated `input` string and submits it in a
branch before the selected turn, reusing that turn's persisted context/workflows.
It does not mutate the original transcript or undo external effects. The user
message editor retains drafts on errors and makes no requests on cancellation.

## Evidence contracts and latency diagnostics

`contracts.py` documents the purpose, arguments, success/error format and field
meanings of Chat-only `read_evidence`, `read_artifact` and `ask_user`. Tool previews
supply exact `read_examples` against the original evidence_ref. `read_evidence`
returns explicit isError, data, source_evidence_ref, offset, total, next_offset,
next_read, truncated, available_paths and note. total measures the value at the
selected evidence path, not a BI catalogue size. Pages may be shorter than limit;
copy next_read rather than calculating offsets or paging a previous page as a new
source. available_paths describes the selected value on success and the root on
path failure. Paths do not include the disposable preview's result/data wrapper.

Discovery coverage distinguishes shown_records, page_records, server total_count,
page and has_next. A general availability question requests a short page (normally
10 entries) and answers from its visible IDs/names plus total; exhaustive listing
uses the original server list tool's pagination when explicitly requested.
This avoids unnecessary schema reads and full-result paging without hiding missing
coverage. Superset MCP tool schemas and descriptions are not changed.

`discovery.py` maintains versioned encrypted checkpoint state for active-turn
queries, visited pages/projections, resource-field fingerprints, exact dataset
matches, inspected schemas, evidence ranges and intervention counters. Query
membership includes connection/tool and filters/search, but excludes pagination,
sort order and selected columns. New records or substantive fields are progress;
transport metadata and timestamps are not. Search includes SQL: a concrete table
name should use `table_name`/`eq` filters, then `get_dataset_info` with its original
advertised schema. When lookup is unresolved, schema-validated next-page hints
use the server's actual pagination. Equivalent spaces/underscores in a complete
requested table name can identify a candidate without rewriting search arguments.
Exact matches and evidence references remain in compact runtime
guidance through context compaction; database/schema ambiguity remains explicit.

Before MCP dispatch, repeated covered discovery requests receive a client-origin
`discovery_repeated` result (`source=chat_runtime`, `external_dispatch=false`) with
source evidence and a corrective next step. Parallel duplicates are deferred until
the first result commits, then checked again. New pages/fields/filters and explicit
refresh requests remain available. Coverage uses returned page sizes and offsets;
a smaller page wholly inside a recorded range is redundant too. Focal discovery
requests explicitly default to 10 records. Unknown totals never imply completeness,
and explicit refresh invalidates that query's prior page coverage. Recorded evidence ranges have the same guard.
Interventions preserve tool-call/result pairs and current authorization checks;
they are not cached MCP executions or permission grants. Three wholly blocked
model generations trigger a final partial answer. Progress and new user steering
reset the guard. Missing tracking state is rebuilt from active-request messages
without executing historical operations; historical transcripts are not rewritten.

Model calls using unavailable or unadvertised tool names receive a recorded,
non-dispatched error with exact currently available names. At most two model
generations may correct such names per turn; further invalid generations fail.
Chat never guesses aliases, rewrites hash suffixes, or dispatches a correction on
the model's behalf. Both execution drivers use this shared validation before
scheduling; canonical call/result pairs and normal authorization remain intact.

Under context pressure, Chat first attempts the compact view, then retains full
schemas for a focused inspection or chart tool set, plus clarification/evidence
access. A successfully loaded chart reference retains its preview/edit/schema
tools, including `update_chart_preview`, even when the active turn has no new
dataset-discovery match. Unresolved lookup keeps discovery available. If that still
cannot fit,
Chat gives an explicitly partial answer; it must not claim unfinished chart work
completed. `tests/ai_runtime/test_discovery.py` and the context/engine tests cover
interception, isolation, replay, exact matches and both pressure-recovery stages.
Model compliance remains provider-dependent; live preview validation complements
these deterministic checks. A form-data link is not proof of a successful query:
verify rendered data before claiming chart success. The focused chart tool set
retains `get_chart_data` for unsaved-chart verification. Distinct schema/evidence
reads can still consume many model rounds; discovery guards do not guarantee
low latency or prevent all unnecessary verification. No MCP server changes or schema migration are involved.

When discovery or context pressure requires a final answer without further tools,
provider requests omit the `tools` field instead of sending an empty array.
Compatible inference servers can reject `tools: []` with HTTP 400. Recorded tool
history remains in the context; disabling tools does not discard prior evidence.

Each provider request emits an encrypted `model_timing` event with generation_id,
duration_ms, time_to_first_output_ms, time_to_first_answer_ms, reasoning_characters,
answer_characters, status and provider usage. It contains no prompts, reasoning
text or credentials. Durations include model-service queue/prefill/decode and
transport; client timing alone cannot separate these. Tool start/completion events
measure tool latency independently. Flat token counters accumulate across rounds;
provider throughput/latency gauges retain their latest value rather than being
incorrectly summed. Per-request usage retains provider cache details when available.
Investigate multiple model rounds and repeated evidence reads before attributing a
slow turn to SQL/MCP. No KV-cache hit is guaranteed by this client.

## Configuration, deployment and verification

Use the [repository commands](../../../README.md#durable-ai-chat) for migration,
the Chat-only dependency environment, worker, scoped purge and deterministic tests.
Enable `AI_CHAT_RUNTIME_ENABLED=true` only in the Chat web and AI worker
environments. Keep the server dependency environment unchanged. The additive
migration is `f1a2b3c4d5e6`; it never deletes conversations or resets settings.
Existing encrypted connection settings remain the shared administrator configuration.

Named model connections, API protocols, the Focal BI MCP destination and user/role
tool restrictions are managed on the administrator-only AI Connection page. New
turns resolve published model IDs on the server; arbitrary endpoints, credentials
and adapters cannot be supplied by the browser. Accepted turns keep their private
configuration snapshot. Model connections and credentials are administrator-owned. Public runtime
metadata exposes only published model IDs, names, connection labels, image capability
and the default. Turn submission accepts `model_id`; the server resolves its exact
connection/revision and pins the private configuration. An active turn never switches
providers. A changed model, endpoint, adapter or revision clears opaque continuation
and reasoning fields while preserving portable messages and tool evidence. MCP still
receives a fresh user/post identity; model selection cannot expand MCP permissions.

Personal MCP token/OAuth routes return 410. Old encrypted MCP account records are
retained without being used for new Chat turns. Administrator model connections use
`models/ai_model_catalog.py`; this is separate from the historical MCP catalogue.
Settings and connection-test APIs reject non-administrators. Masked test/verify keys
resolve only against their saved connection and destination. Changing destinations
requires a new key. Shared MCP/agent saves are separate from model verification and
model publication; older clients cannot erase role/user restrictions by omission.

### Model catalogue and verification

`model_catalog.py` owns named model connections, discovery, revision-bound capability
probes and publication. Additive migrations `b3c4d5e6f7a8` and `c4d5e6f7a8b9` create
Chat-only tables using binary encrypted storage. Saved provider profiles are imported
on the first catalogue load without network calls; the active model is grandfathered
as a published legacy entry. Other imported/discovered models require verification.

Admin endpoints under `/api/v1/ai_connection/models/` expose the catalogue,
`connections/verify`, `{model_id}/verify`, `jobs/{id}`, `publish`, and connection delete.
Verification is a durable queued job processed by the existing AI dispatcher; the
browser polls its status. A bounded models request discovers IDs, but only the
selected test model is probed. A synthetic tool round-trip never calls BI tools.
A separate random two-panel color image probe marks image support; failure retains text/tool
eligibility. Successful connection edits replace credentials atomically, advance the
revision and invalidate other models' checks. Failed checks preserve working settings.
Candidate credentials are erased from completed/failed jobs. Interrupted jobs expire
after six minutes; operators may repeat verification. Provider bodies are not logged.

The right-side settings panel drafts an ordered published list and a required default.
Moving unverified models right queues probes. Save publishes atomically. Missing models
remain identifiable but unavailable; unpublished, stale or missing models cannot serve
new turns. Existing accepted turns retain snapshots. The runtime feature flag disables
new submissions for rollback without replaying them through another engine.

### Private images and composer

`images.py` stores metadata-free PNGs encrypted in the shared metadata database.
Uploads accept decoded JPEG, PNG and static WebP only. Defaults are four distinct
images across retained history, 5 MiB per image and 20 megapixels per image, configured
by `AI_IMAGE_MAX_COUNT`, `AI_IMAGE_MAX_BYTES` and `AI_IMAGE_MAX_PIXELS` on web/worker.
The browser uploads drafts with `POST /api/v1/ai/images/`, submits `attachment_ids`,
and uses authenticated `GET /images/{id}` previews. DELETE removes only unbound drafts.
Acceptance binds references transactionally; replay/fork/retry/edit share references.
User/post checks guard every upload/preview/removal and inference hydration. Unbound
drafts expire after 24 hours. Bound image data is retained with conversation evidence.

Canonical messages contain image references, never image bytes. Provider adapters
hydrate native Chat Completions or Responses image content immediately before inference.
Image limits and model capability are enforced server-side, including retained images;
images are never silently dropped. The message input occupies a full-width row;
attachment sits on the left of the bottom row, with confirmation mode, model,
context usage and send/stop controls grouped on the right. The composer supports picker, paste and drop with
thumbnails, progress, retry and removal. Only published model choices appear to users.
An unavailable saved model requires explicit replacement. Model choice is frozen while
a turn runs; text steering and Stop remain available. Retry/edit use the selected model.

Conversation menus use the existing owner/post-scoped session update and delete
APIs. Migration `a2b3c4d5e6f7` adds `ai_chat_session.is_pinned`, defaulting to false.
The session list orders pins before its requested sort before pagination; renames
and pin changes are partial updates, preserving each other's fields. Delete still
rejects active turns. The UI requires deletion confirmation and retains the row
when a request fails. Saved BI resources are outside conversation deletion.

Roll out to internal users first. Pin runtime version per conversation. Rollback
disables new submissions with the flag and routes the normal page to legacy Chat;
existing runtime records and in-flight execution remain available for inspection.
Never replay runtime turns through the legacy engine. A schema downgrade is not
an operational rollback and should only run after retaining any required records.

Run `tests/ai_runtime/live_evaluation.py` separately against staging with dedicated
test data and a configured provider. It creates tagged Chat test conversations and
performs real HTTP submission, duplicate submission, reconnect and event replay.
Review the returned evidence, not just completion status. Browser checks cover
desktop/mobile, keyboard, steering, approval, reconnect and native chart artifacts.
`tests/ai_runtime/live_stream_load.py` measures commit-to-delivery event latency
with five simultaneous turns and forces an SSE reconnect for every turn. The
separate `live_artifact_flow.py` creates a dedicated preview/save/edit fixture;
its saved test chart is retained for inspection. The scoped Playwright
configuration is `superset-frontend/playwright/ai-runtime.config.ts` and accepts
an explicitly prepared local storage state through `AI_BROWSER_AUTH`.
The release requires at least 90% successful BI tasks per enabled agent profile,
zero unauthorized effects/disclosures, durable restart/recovery, and acceptance
p95 under one second and event visibility p95 under two seconds at five turns.

Operator logs identify turn IDs, safe error codes, exception types and stack
locations without exception bodies or credentials. The turn snapshot provides
tool failures, usage, cancellation, artifacts, pending requests and uncertain
outcomes; the persisted event sequence provides the audit trail.

## TODO: Harden KV-cache reuse

Planned work, not implemented or verified. Make model requests preserve the
longest valid reusable prefix while retaining provider neutrality, current
permissions and correct conversation context. Application-side hardening cannot
guarantee cache hits when an inference server lacks caching or evicts an entry.

- [ ] Make prompt construction deterministic: stable instruction blocks, tool
  ordering, schema serialization and connection guidance. Keep changing context
  at the end; avoid repeatedly appending identical guidance. Preserve original
  message roles, tool-call IDs, results and provider-required continuation fields.
- [ ] Version and fingerprint the model-visible prefix and relevant configuration.
  Validate actual prefix continuity before using provider response IDs or message
  offsets. Invalidate continuation safely after compaction, model/profile changes,
  instruction/schema changes, permission changes and edited branches; never reuse
  a response ID solely because the message count fits.
- [ ] Make bounded-context views stable across successive requests. Persist and
  version compaction boundaries and summaries instead of rewriting older context
  unnecessarily. Preserve evidence references and valid tool-call/result groups;
  prioritize authorization and context correctness over cache preservation.
- [ ] Add capability-gated provider cache hints, routing keys, breakpoints and
  retention options where supported. Keep settings administrator-owned and scope
  application cache identifiers to the authorized user/post/connection context.
  Unsupported providers must work without cache-specific fields. Any inference
  server configuration change requires a separate, reviewed deployment step.
- [ ] Record provider-reported cached input tokens/cache reads and writes, input
  usage and time to first token. Distinguish reported hits from estimated reusable
  prefixes and unavailable metrics. Never log credentials or raw prompts for cache
  diagnostics, and never treat reduced transmission as proof of KV-cache reuse.
- [ ] Add deterministic request-capture tests for follow-ups, tool loops, restarts,
  forks/edits, configuration changes, permission revocation and compaction. Verify
  unchanged prefixes and safe invalidation, with no cross-user/post context reuse.
  Benchmark repeated BI tasks on each configured caching-capable provider and
  report measured hits, latency and token usage; document non-caching fallbacks.

Acceptance: ordinary follow-ups extend the prior model-visible context without
unnecessary prefix changes; continuation never drops or duplicates context;
revoked tools/data cannot survive through cache optimization; supported cache
metrics demonstrate reuse in live evaluation. Retain the protected Superset MCP
server boundary: no server or behavior-affecting dependency/configuration changes
without the user's separate explicit confirmation.


### Context usage and reasoning diagnostics

The composer ring shows input plus output tokens for the latest model request,
relative to that turn's configured context window. It is not cumulative billing
usage. Before the response completes it uses the serialized-request estimate;
provider usage replaces that estimate on completion. The tooltip identifies the
source and shows the output limit, input allowance and tool-result reserve.
Usage persists in the turn checkpoint and reloads with the turn snapshot. A model
selection change hides an unrelated model's measurement until its next request.

Reasoning display uses the connection preference documented above, bounded to
12,000 characters per generation. Expired worker leases mark unfinished activities
interrupted with a recovery reason. Streaming lease checks renew ownership alongside
the ten-second heartbeat; this does not prevent recovery after a stopped or
unreachable worker. Cancellation is displayed separately. Increasing token budgets
does not extend worker leases.
