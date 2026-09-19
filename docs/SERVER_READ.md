# Read-only server diagnostics

Mark can inspect operator-published diagnostics through `server.read`, and the
owner can request `/server status`, `/server config`, or `/server events` in
Telegram. This capability does not provide SSH, arbitrary commands, filesystem
paths, raw logs, Docker access, credentials or unrelated services.

The fixed sections are:

| Section | Published information |
| --- | --- |
| `status` | Host disk capacity/free space; running/restarting/OOM state, exit/restart counters and image digest for the three Mark containers; guardian service state and known release phase. |
| `config` | Typed, allowlisted runtime budgets, model/reasoning settings, timezone and semantic-search flag. The bridge's provider settings are authoritative. |
| `events` | Counts of fixed technical error categories and known Mark package module/line references from the latest 200 log lines within ten minutes, plus at most 50 observed container/guardian state changes. No raw log text or exception messages. |
| `guardian_source` | The public installed guardian Python source, checked for protected ownership before publication. |
| `observer_source` | The public installed diagnostic collector source, under the same checks. |

Use `self.inspect` for Mark's own runtime source. The diagnostic source sections
are data for review and do not grant permission to change or execute host code.

## Trust boundary

The root-owned `marka-observer.service` runs a fixed Python collector. Its Docker
queries name only `marka-mark-1`, `marka-bridge-1` and `marka-sandbox-1`; the inspect
format selects specific state fields without requesting container environment
variables. The sole systemd query is the activity of `marka-guardian.service`.
No model input is passed to these commands. Process output and runtime are
bounded while being read, and subprocesses receive a minimal environment.

The collector writes sanitized JSON snapshots atomically to
`/var/lib/marka-guardian/observability`. The deployment must create this root-owned
directory before enabling the service. The unit uses a read-only host filesystem
except for that output directory, a private temporary directory and Unix sockets
only. It refreshes once after boot and roughly every minute after a run finishes.

Only the unprivileged protected bridge receives a **read-only mount** of those
snapshots. Its optional root-owned `server_snapshot_dir` configuration selects
the mount. The bridge checks fixed section names, file/directory ownership,
permissions, symlinks, file size and the snapshot envelope before returning text.
Each validated read attempt is independently recorded in its protected journal
as timestamp, section and success/failure; it retains the latest 2000 attempts.
No output text, request paths or credentials enter that audit.

The mutable bot calls the bridge RPC. It receives no host filesystem mount or
Docker socket. The model cannot select another path, service, container, command
or log range.

## Freshness and pagination

Responses include `generated_at`, `age_seconds` and `stale`; observations older
than 180 seconds are marked stale. A failed collector leaves the last available
snapshot readable with its original timestamp. A successful collection may also
report an individual service as unavailable. Neither is proof of current health.
Log categories are indicators, not a diagnosis or complete incident history.

Pages are limited to 12,000 characters. Continue with the returned `next_offset`
and `sha256` as `expected_sha256`. Continuations without a digest are rejected,
as are offsets beyond the content and changes to the content between pages.
Refreshing a timestamp alone does not invalidate unchanged source pagination.

This is an observation mechanism. It cannot restart services, alter the guardian,
change provider settings, inspect personal conversations or recover a failed
host. Existing guardian recovery and operator deployment remain separate.
