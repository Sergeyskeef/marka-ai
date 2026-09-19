# Managed connections and secrets

Mark can discover and check its installed connections without seeing credential
values. The protected bridge reads a credential only when the corresponding
fixed capability needs it. Tokens, keys, OAuth state, credential paths and key
fragments are never returned to the bot, model context or diagnostic audit.

`connections.list` returns the fixed references `codex`, `telegram`, and
`openai_speech`, whether each is configured, its allowed capabilities and any
fresh cached availability result. Listing does not perform authentication or
read key contents. An untested connection has unknown availability.

`connections.check` accepts only one of those references:

| Connection | Check | What success proves |
| --- | --- | --- |
| `codex` | Official CLI login status | A local ChatGPT login is present; `verification_scope=local_login`. No model request runs, so this does not prove remaining quota or successful inference. |
| `telegram` | Bot API `getMe` | The installed token authenticates the bot; `verification_scope=bot_identity`. Only its username and bot flag are returned. No message is sent and no owner/account IDs are returned. |
| `openai_speech` | Validate the protected key file, then GET the fixed `gpt-4o-transcribe` model metadata endpoint | The API accepts this metadata request; `verification_scope=model_metadata`. This does not prove transcription endpoint permission, available billing or a successful audio upload. Both `transcription_verified` and `billing_verified` remain false. |

The speech check uses the documented
[OpenAI model retrieval endpoint](https://developers.openai.com/api/reference/resources/models).
It sends no audio and starts no inference. Its URL and method are fixed; TLS
verification stays enabled, environment proxies are disabled, redirects are
rejected and response size is bounded. Error bodies, headers, provider request
IDs and arbitrary exception messages are discarded. A restricted key may allow
transcription while forbidding model-metadata reads, so an `access_denied` result
is a failure of this check, not proof that every allowed action is unusable.

Checks have a 25-second caller deadline and results, including failures, are
cached for 60 seconds. Parallel requests share a check. Disconnecting a caller
does not start another check on retry. Each result includes a fresh locally
generated `request_id`, observation time and cache information. Availability is
always qualified by the check's scope and time.

Every validated list/check request is independently audited in the bridge's
bounded read journal as `connection:list` or `connection:<reference>` plus time
and success/failure. No secret, check result text or arbitrary request field is
stored in that audit.

The existing capabilities continue to use credentials inside the bridge:
structured Codex inference with the ChatGPT login, Telegram operations limited
to the paired owner and owner-submitted files, and OpenAI transcription of
validated owner voice messages. Their existing budgets, input validation,
receipts and retry rules still apply. A connection listing is not a new grant of
unrestricted API access.

This release does not install arbitrary connections, reveal/export secrets,
rotate keys, change permissions or accept caller-selected URLs, headers, paths,
HTTP methods or shell commands. Adding another service requires an explicit
operator-owned capability with its own input/output contract and checks.
