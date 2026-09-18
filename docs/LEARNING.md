# Learning from observed work

Mark records what happened, proposes scoped lessons, and carries useful procedures into later work. The underlying model weights do not change. Task status `completed` is a model claim, and a process exit of zero is an execution result; neither establishes that the owner's whole request is correct.

## Durable evidence

`Learning.record_job(job_id)` runs after a task reaches a terminal state. It reads the full canonical tool events from SQLite, checks their job and tool identity, and ignores the abbreviated model trace as evidence. Currently the supported scopes are `code.run`, `workspace.read`, and `self.experiment`.

The learning ledger retains source content, SHA256, event IDs, task IDs, operation identity and observed outcomes. It distinguishes a failed process, a timeout, a zero exit, an unsuccessful experiment, and a completed regression comparison. Text printed by a program cannot upgrade the process result.

Source snapshots survive ordinary raw-event retention. Exact evidence can be read in bounded pages. Summaries show recent evidence while aggregate counts cover all linked observations. Multiple events or restarts of the same job do not count as independent support. Scheduled repetitions with the same root task count as one independent task.

## Procedural candidates and reuse

Reviewed templates turn a small set of observed situations into L2 lesson candidates:

- A failed process or timeout requires diagnosis and another bounded check.
- A failure followed by a zero exit of the same command records a recheck; it does not prove why the result changed.
- A successful invocation of a recognised Python or Node test command preserves that command as a reusable example, with a reminder to verify discovery and coverage.
- A rejected workspace read suggests checking the path and reading in pages.
- A rejected or incomplete code experiment preserves the original version and reports the failed or missing comparison.

Examples are historical data. They are not commands that the learning module executes. Applying a lesson does not grant new tool capabilities or permission to publish, change identity, access private data or spend money.

All generated lessons use `kind=lesson`, `level=2`, `status=candidate`. Explicit owner acceptance retains that classification. A model-generated free-form lesson stays review-only regardless of how often it is proposed. Only the fixed templates qualify for automatic procedural guidance.

`Learning.applicable(query, tools=..., limit=4)` selects a small set of relevant procedures by explicit tool scope and a bounded vocabulary. This routing is not semantic understanding. Returned records label the application as `owner_accepted`, `tentative_procedural`, or `automatic_procedural`; the canonical memory status remains visible.

`Learning.record_use(job_id, memory_ids)` records that a lesson was selected into a task's context, once per task. This is an exposure count, not proof that the agent followed the lesson or that it caused success.

## Owner policy and feedback

The library default is `tentative`. A directly authenticated owner command can change policy, with its source event and snapshot retained:

| Mode | Candidate behaviour |
| --- | --- |
| `off` | Store observations and candidates; use only owner-accepted lessons. |
| `tentative` | Relevant fixed templates may appear as tentative procedural hints. |
| `auto` | A fixed template with support from at least two independent tasks and no current negative feedback may appear as automatic procedural guidance. Below that threshold it remains tentative. |

Automatic use never changes a candidate to accepted and never automatically installs code. Owner-accepted free-form lessons are separate from template eligibility.

`Learning.feedback(job_id, valence, note, source_id=...)` attaches a positive or negative owner assessment to an actual finished, failed, blocked or cancelled task. Replaying the same source event has no extra effect. The latest owner assessment for that task is current; previous assessments remain in the audit.

Feedback is linked to both lessons supported by that task and lessons selected during it. Current negative feedback suspends their automatic/tentative selection pending review. `filter_context` also excludes affected procedural memories from general prompt/retrieval paths. It does not establish which individual lesson caused the bad outcome, so no accepted knowledge is silently rewritten. Exact owner inspection remains available through `/memoryid` and `/why`.

`review_batch(before_id=..., limit=5)` returns paged candidates with scope, observed outcomes, sources, feedback and use counts. `details(memory_id)` exposes the same evidence summary for a known lesson. Forgetting a template prevents a later similar failure from recreating it automatically. Its source evidence is excluded from active learning recall.

## Bounded optional reflection

`await Learning.reflect(complete, every=3, daily_limit=8)` may consolidate a batch of tool-using tasks into up to three review-only proposals. The caller supplies the ordinary budgeted model callback. Simple conversations without supported observed results are not eligible.

The default is one inference after every three eligible tasks, with an independent cap of eight reflection calls per UTC day. A persistent claim and watermark are written before inference. Errors and interrupted calls consume that claim, preventing automatic retry loops after restart. All returned source IDs and scopes are validated before saving any proposal.

Reflection receives bounded data and explicit uncertainty requirements. It cannot accept memories, change policy, invent evidence IDs, execute tools, or install proposed code. Model reflection and task verification remain separate.

## Integration contract

1. Finish the durable task, then call `record_job(job_id)` independently of delivery success.
2. Select scoped procedures for a later task and record selected IDs with `record_use`.
3. Route owner policy and feedback commands through the authenticated command handler; never expose policy mutation or owner acceptance as model tools.
4. Show candidate provenance and paged evidence during owner review.
5. Invoke optional reflection through the same provider budget used by normal work. A reflection failure must not replace an already completed task result.

The lifecycle tests use real temporary SQLite databases and fake model callbacks. They cover replay and crash recovery, contradictory owner feedback, independent support, false success claims, source retention, candidate boundaries and reflection limits.

## Telegram and CLI controls

The paired owner can use `/good [task-id] [note]` or `/bad [task-id] [note]`; without an ID the latest terminal task is selected. A stable command source prevents replay from changing the target or duplicating feedback. `/learning off|tentative|auto` records the owner's policy decision.

`/review [cursor]` and `/candidates [cursor]` page through proposed knowledge. `/memoryid id [offset]` reads a memory; `/source event-id [offset]` reads evidence; `/why memory-id [source-id [offset]]` exposes provenance and immutable source snapshots. These are inspection paths, not automatic acceptance.

`/progress [task-id]` shows durable steps, checks, artifacts and remaining budget. `/extend task-id` adds one configured allowance and resumes an unfinished task. Duplicate delivery of that command cannot add the allowance twice.

Idle maintenance indexes at most four sources per pass in a worker thread. Optional reflection uses the shared model budget and is cancelled when a new task arrives. Index writers share an exclusive lock with `marka models index --limit N`. `marka models status` is local; `marka models install` explicitly downloads the pinned optional assets. `marka import-archive file.jsonl --source label` imports history as unverified source events.

Text documents from the paired owner's original private messages may be saved to the workspace, up to 512 KiB. Their caption supplies the instruction; file contents remain data. Without a caption, the default request is a brief summary. Incoming code is not executed on receipt. PDF, images, audio and video receive an explicit unsupported-format response.
