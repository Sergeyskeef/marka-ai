# Recoverable self-upgrades: implementation contract

Target: the owner can ask Mark to improve itself, and Mark can submit a tested
candidate for installation. Recovery must run independently of that candidate.
This is the implementation contract for 2.4. Release evidence is tracked
separately in VALIDATION.md; a checkout alone does not enable protected deployment.

## Trust boundaries

1. The mutable bot retains its workspace and canonical database. It never gets
   Docker access, host shell, guardian files, or provider/Telegram credentials.
2. A pinned bridge container owns the single official Codex authentication home,
   the Telegram token, and the OpenAI speech key. The original Codex directory
   is mounted in place: no OAuth copy or parallel refresh chain. The bridge has
   an independent SQLite journal of inbound owner updates and remote effects.
3. A root-owned host guardian controls fixed bot/container resources. Its code,
   release manifests, known-good image IDs, and database checkpoints are outside
   every mutable bot mount. Candidates cannot submit Dockerfiles, shell commands,
   arbitrary image names, dependencies, host paths, or guardian changes.

The bridge persists incoming owner updates before advancing the Telegram offset.
The mutable client reads the journal by offset, so database recovery can replay
inputs even after Telegram acknowledged them. Unknown remote effects stay
uncertain; they are never automatically resent after a crash.

## Shared interface for implementation

- `Settings.bridge_socket`: string, default empty; environment
  `MARKA_BRIDGE_SOCKET`. Direct mode remains for local development and existing
  installations. Production guarded mode has no direct credentials.
- New `marka.bridge_client` exports `BridgeProvider`, `BridgeTelegramClient`,
  `bridge_transcribe(socket, audio, *, source, attempt, duration, timeout)`, and
  `bridge_status(socket)`. Clients use bounded length-prefixed JSON over a Unix
  socket. No exception or response contains credentials or raw provider errors.
- `BridgeProvider` has existing provider `complete(prompt,schema,images=())`
  and `status()` interfaces; optional request identity supports remote receipts.
- `BridgeTelegramClient` matches the existing Telegram client API. Sends accept
  optional `effect_id`, derived from durable delivery identity plus payload hash.
  Arbitrary Telegram API methods and chats are rejected by the bridge.
- The bridge serves only the paired owner's original private messages, journals
  raw updates, and validates file IDs against those messages before downloads.
  `/rescue` and `/rollback` are owner recovery controls persisted independently
  of the mutable bot. Speech and model calls use bounded durable effect receipts.
- `Settings.upgrade_inbox`: default empty; `MARKA_UPGRADE_INBOX` points to a bot
  writable request directory. Guardian state/results are a separate read-only
  mount (`MARKA_UPGRADE_STATUS`). `self.request_upgrade(id)` exports exact
  archived candidate/baseline bytes and hashes, experiment ID, root owner task,
  and a durable request ID; no command, image name or arbitrary path.
- A request contains format version 1, `request_id`, `experiment_id`, `job_id`,
  `source` (original `telegram:<update-id>`), `objective`, `baseline` and
  `candidate` dictionaries of source path to UTF-8 text, and their canonical
  SHA-256 manifests. Only `src/marka/*.py` changes; supplied tests are evidence,
  never a replacement for the guardian's pinned acceptance checks.
- A bot heartbeat in its private state describes startup, event-loop tick,
  worker progress and current job. The guardian checks Docker state and the
  database itself as well; a self-reported ready flag is not sufficient.
- Runtime capability context reports actual installed features, requested model
  and unknown resolved model explicitly. It must not invent a GPT generation.

## Upgrade and recovery sequence

`requested в†’ validating в†’ waiting_idle в†’ checkpoint в†’ activating в†’ probation
в†’ accepted`; failures after checkpoint enter `rolling_back в†’ recovered`.

The guardian serializes requests and journals transitions atomically with fsync.
It captures candidate bytes before checking them, rejects a stale baseline and
duplicate rejected candidate, builds an overlay on a pinned image with no
dependency installs, and evaluates it with synthetic state and no credentials.
Acceptance includes independent host-side observations, not only candidate test
output. Source manifests bind the checked bytes to the installed image.

It waits for an idle work boundary, stops the sole mutable bot, makes a checked
SQLite snapshot outside the bot volume, and activates the candidate. The bridge
keeps collecting incoming messages throughout. Probation observes process exits,
restart/OOM counters, heartbeat age, task deadline and canonical DB integrity.

Recovery restarts the known-good image even if the bot cannot import or answer.
If the database is intact and compatible, preserve it. If restoration is needed,
quarantine the failed database first, restore a checked checkpoint, and block
unfinished snapshot jobs before replaying the independent inbound journal.
Remote effects with uncertain outcomes require review; recovery must not silently
repeat payments, model requests or Telegram deliveries. The original fallback
image remains available across later upgrades.

## Honest limits and acceptance

Code rollback is not a proof of correct reasoning. Same-process unit tests can be
fooled by arbitrary Python, so they are regression evidence, not a security proof.
Incoming messages are recoverable from the independent journal; arbitrary files
or intermediate computations produced only in a failed version are not promised
lossless recovery. Credentials and recovery checkpoints remain outside its reach.
Hardware failure still requires an off-host backup. The design does not grant
trading, payments, publication or unrelated external account permissions.

Required synthetic drills: import crash, hang, invalid database, guardian restart
during activation, duplicate/stale request, disk reserve failure, and recovery
with new incoming messages and uncertain remote effects. Actual production
installation follows successful drills and a fresh state-preservation check.
