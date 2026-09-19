# Codex model and reasoning settings

Mark uses the official Codex CLI with a ChatGPT login. Model settings do not
enable API-key billing or change the provider. Native Codex tools remain disabled;
Mark's runtime validates and executes actions.

## Explicit operator settings

For a standalone installation, set `model` and `reasoning_effort` in Mark's
`settings.json`, or use `MARKA_MODEL` and `MARKA_REASONING_EFFORT`. For example:

```json
{
  "model": "gpt-5.6-sol",
  "reasoning_effort": "high"
}
```

These are fields to merge into an existing configuration, not a replacement for
the full settings file. Omitted/null fields preserve Codex's defaults. An empty
string is rejected. Explicit `"none"` is a distinct setting from null and should
only be selected when the actual model supports it.

For the protected deployment, the host operator sets these fields in the
root-owned bridge JSON configuration and restarts the bridge after validation.
The optional `reasoning_effort` field is backward compatible with existing bridge
configurations. The protected bridge's settings are authoritative: mutable bot
settings and environment variables cannot override them. Model requests cannot
supply a provider, model, reasoning level or arbitrary profile.

The provider passes `--model <model>` and
`-c 'model_reasoning_effort="high"'` explicitly. It keeps
`--ignore-user-config`, `--ignore-rules`, ephemeral sessions, the read-only
sandbox, structured output and every native-tool restriction. The fourth
positional `CodexProvider` argument remains the timeout; `reasoning_effort` is
keyword-only.

## What status proves

Provider and bridge status expose the requested model and reasoning effort as
`model_requested` and `reasoning_effort_requested`. Both corresponding
`*_resolved` fields remain null: the current structured CLI event stream does
not supply independently verified resolved settings. Login status proves only
the authentication method and availability of the CLI, not successful inference.

An omitted setting means Codex selects its default. The CLI banner's `reasoning
effort: none` can also represent an unset option; it is not evidence that a model
performed no reasoning. A model's own answer about its identity is not runtime
evidence. Keep catalog observations, explicit settings and successful real
requests separate when reporting a deployment.

The production Codex catalog inspected on 2026-09-19 advertised `gpt-5.6-sol` with
default reasoning level `low` and support for `low`, `medium`, `high`, `xhigh`,
`max` and `ultra`. This is a dated account-specific catalog observation, not a
guarantee of future availability. The syntax validator accepts known CLI effort
names; it does not assert that every model supports every name.

Before a model change, verify the current official CLI catalog, then run a small
structured inference smoke test with the proposed settings and existing
isolation contract. Compare useful task results and latency before assuming a
higher effort improves Mark. High effort can consume more time and account
capacity. Do not fall back silently to another model or API-key provider.

The [official Codex configuration reference](https://developers.openai.com/es-419/docs/config-file/config-reference)
documents `model_reasoning_effort` and explicit configuration overrides. The
installed CLI and its current model catalog determine available combinations.

This release intentionally provides one fixed operator-controlled configuration;
per-task model routing needs separate outcome measurements and receipt handling.
