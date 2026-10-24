---
title: Durable AI Chat runtime
hide_title: true
sidebar_position: 9
---

# Durable AI Chat runtime

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

## Canonical action policy

Application security and execution policy have highest priority, followed by
administrator BI guidance, explicit user intent and accepted steering, selected
versioned workflows, then sourced connection guidance and retrieved data. Tool
results cannot grant permissions or approve actions.

Exploration previews charts. Direct, bounded save/edit instructions can execute
within their target scope; ambiguous targets require a question or confirmation.
Destructive, access-changing and unclassified operations require approval.
Approvals bind the connection/version, user/post, schema, tool and normalized
arguments. Changing any bound value invalidates approval. Existing Superset
permissions still authorize the actual tool invocation. Third-party annotations
are preserved metadata; administrators classify tools independently. SQL execution
is unclassified because even apparently read-only SQL can have effects.

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

`context.py` builds a disposable model view; canonical messages, tool outcomes,
operation records, approvals and artifacts remain unchanged in encrypted storage.
Connection guidance is injected once per request, ahead of history. Historical
copies from older turns are excluded from the view, not deleted from the ledger.

Identical tool results with the same tool/normalized arguments share an evidence
reference in the view. This never skips tool execution or reuses a stale read.
Changed results remain distinct. Native structured content replaces duplicated
raw/text representations in large previews. Large arrays, fields and nested
results have explicitly marked previews with paths/pages available through
`read_evidence`. Call IDs address tool results; `message:N` addresses an exact
canonical historical message. Retrieval refreshes the current actor's authorization
and remains confined to that turn's user/post-scoped conversation. It cannot grant
permission or authorize a write.

When needed, complete assistant-call/result groups are replaced with deterministic
structured excerpts, resource/filter facts and evidence references, including groups
inside the active turn. Summaries are versioned and source-hashed in checkpoint
`context_memory`, reused after recovery and carried to subsequent completed turns.
Rolling memory retains the initial/recent request excerpts and recent resource facts;
older ranges stay retrievable. These are bounded extracts, not model-generated semantic
summaries: the agent must retrieve exact evidence when decisions or effects are unclear.
The latest request, attached images and incomplete call groups are never silently cut.
Private reasoning is excluded from summaries and historical-message retrieval.

Dataset discovery previews retain IDs/names across the returned page. Dataset
schema previews keep actionable column names/types and metric expressions rather
than verbose SQL/audit metadata. The newest complete tool-result group stays in
context so the agent can act on it instead of repeatedly rediscovering resources.
Its bodies are progressively projected if a recent parallel batch alone exceeds
the allowance; assistant call IDs and matching result messages remain paired.

`evidence.py` resolves structured or single text-backed JSON results to a common
data root. Model previews expose `evidence_ref`, `available_paths`, `result` and
the original error status without repeating raw transport payloads. `read_evidence`
paths start at this data root (for example `datasets`), not at the preview's
`result` wrapper. Explicit legacy envelope paths remain supported. Invalid paths
advertise root keys. Reads bound strings, nesting and serialized size as well as
item count, mark excerpts and provide cursors; deeper paths retrieve excerpted
fields. `next_read` carries the original evidence ID/path and actual next offset;
out-of-range reads of an already returned page point back to that cursor.
Original encrypted evidence is unchanged.

Overlapping discovery records are collapsed in the disposable view only within
the same namespaced tool, filters and sorting. Changed projected records remain
visible, with earlier evidence references for unchanged overlaps. This does not
prove complete catalogue coverage or skip an external read. Within a turn, three
consecutive successful `list_*` reads without new/changed records (or payloads
without IDs) in the same connection/query scope, three repeated successful evidence
pages without new content, or three consecutive failed evidence lookups,
switch the next model request to an answer-only pass. The agent must answer from
collected evidence and explain gaps. Further tool requests fail explicitly rather
than continuing an unbounded loop. Writes never participate in this safeguard.
If at least six evidence reads keep a compacted view at 95% or more of its input
allowance, the runtime also reserves an answer-only pass. Removing schemas frees
room to restore recorded evidence for that answer. The checkpoint records
`finish_reason=context_pressure`; the answer must identify unfinished work or
partial coverage. Steering resets these turn-local progress guards. This does
not increase the inference server's context size or authorize another operation.

Before dispatch, the Chat-side policy limits Focal dataset/chart/dashboard list
pages to at most 25 items. A divisor of the requested size preserves the starting
offset when changing a 1-based page number. Dataset lists default to ID/name,
schema, database and description; explicitly selected fields remain unchanged.
The original schema validates effective arguments, and result `request_policy`
reports those arguments so subsequent pages use the effective size. This is not
a server configuration or schema change. External tools retain their original
request semantics; generic result bounding and loop safeguards still apply.

The input estimate includes tool schemas and 4096 tokens per image, before private
image hydration. Text uses a UTF-8 byte heuristic (three bytes per estimated token),
not an exact provider tokenizer. Output and upcoming tool-result capacity are reserved.
Unknown models default to a 32768-token window, 4096 response tokens, 4096 tool-result
reserve and a separate 96000-character history ceiling. The verified official
`api.deepseek.com` V4 Flash/Pro and Flash IDs use a 128000-token operational cap,
below the [provider's documented window](https://api-docs.deepseek.com/quick_start/pricing/).
This exception does not apply to similarly named models at custom endpoints. Operators can override these
Chat-only values per exact model ID in `AI_RUNTIME_MODEL_CONTEXT_LIMITS`, for example:

```python
AI_RUNTIME_MODEL_CONTEXT_LIMITS = {
    "my-model-id": {
        "context_window_tokens": 65536,
        "response_tokens": 8192,
        "tool_result_tokens": 4096,
        "context_chars": 160000,
    },
}
```

Configure measured model limits; these settings do not enlarge an inference server's
window. Values are snapshotted at turn acceptance. Provider usage remains authoritative.
If required policy/guidance, schemas, images or the current input alone cannot fit,
the runtime reports that constraint instead of suggesting a branch with the same history.
Checkpoint budget statistics separate schema tokens, fixed instructions and the
input allowance. Fixed instruction/schema overflow is distinguished from an
oversized current request or required call structure after evidence compaction.
Responses continuation is reused only when the exact prior input-prefix hash matches;
compaction, edits or changed guidance force full input without a stale response pointer.
No model/provider switch occurs during a turn. This enables stable request prefixes;
it does not guarantee inference-server KV-cache hits.

Verify with `tests/ai_runtime/test_context.py`, `test_engine.py`, `test_providers.py`
and `test_store.py`, using the focused runtime test command in the repository README.

## Chart follow-up references

`artifact_memory.py` exposes a small chart index plus the Chat-only `read_artifact`
tool. It resolves the latest permitted chart or an exact artifact ID inside the
same conversation, user and post. Native chart/dataset access is rechecked on
retrieval. Full snapshots include form_data, preview cache key, saved/preview state,
provenance and the original MCP request config. Metadata reads of the same cached
preview can recover its originating config. These references survive refresh,
compaction and conversation branches; they do not authorize writes.

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

## Components and contracts

- `store.py`, `models/ai_runtime.py`: scoped turn service and authoritative ledger.
- `runner.py`, `worker.py`: leases, checkpoints, dispatch, recovery and identity refresh.
- `engine.py`, `context.py`: one model/tool loop and bounded context views over full evidence.
- `providers.py`: compatible Chat Completions and OpenAI Responses streaming.
  Provider continuation data, including opaque DeepSeek tool protocol fields,
  stays encrypted. Compatible self-hosted profiles can opt in to a separate
  visible model-reasoning copy; opaque hosted-provider continuation stays private.
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
data. Compatible self-hosted profiles can explicitly opt in to a visible copy;
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

The Responses adapter consumes public `reasoning_summary_text` delta/done events
and final summary arrays ([provider event contract](https://developers.openai.com/api/reference/resources/responses/streaming-events)).
It does not enable reasoning automatically or expose encrypted reasoning or
reasoning-text events. Named `custom`/`lmstudio` connections support the administrator
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
empty disclosures. No extra summarization call is made. Visible summaries or model
reasoning prevent automatic retry after partial output.

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

Under context pressure, Chat first attempts the compact view, then retains full
schemas for a focused inspection or chart tool set, plus clarification/evidence
access. Unresolved lookup keeps discovery available. If that still cannot fit,
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
images are never silently dropped. The composer supports picker, paste and drop with
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
