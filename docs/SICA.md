# SICA and Mark's self-improvement experiments

Reviewed 2026-09-18 against upstream commit
`ed8275dca4d3c5dbf77229964351fe9b424797dc`.
[SICA](https://github.com/MaximeRobeyns/self_improving_coding_agent) is MIT licensed,
copyright 2025 Maxime Robeyns. Mark adapts the mechanism; no SICA source or its
dependencies are bundled.

The useful mechanism is a real cycle: benchmark an agent, archive its code and
results, let an archived agent edit a separate candidate, then benchmark again.
The archive contains individual task outcomes and execution traces, not only a
single aggregate score. The improvement archive is mounted read-only.
[Runner source](https://github.com/MaximeRobeyns/self_improving_coding_agent/blob/ed8275dca4d3c5dbf77229964351fe9b424797dc/runner.py).

The public checkout enables only GSM8K by default; its runner samples 18 problems
with seed 1. It chooses a recent base above the best agent's lower confidence
bound. The meta-edit process exiting successfully does **not** establish improved
task performance. Its benchmark execution mount also exposes the experiment
archive read/write; Mark does not adopt that arrangement.
[Benchmark registry](https://github.com/MaximeRobeyns/self_improving_coding_agent/blob/ed8275dca4d3c5dbf77229964351fe9b424797dc/base_agent/src/benchmarks/__init__.py),
[runner](https://github.com/MaximeRobeyns/self_improving_coding_agent/blob/ed8275dca4d3c5dbf77229964351fe9b424797dc/runner.py).

The authors report improvement from 17% to 53% on a fixed random subset of SWE
Bench Verified. This is their research result, not a result measured for Mark.
The method changes agent software rather than model weights; the paper discusses
observability and additional safety evaluations.
[Paper](https://arxiv.org/html/2504.15228v1).

## The bounded adaptation

Mark can inspect its public source and propose edits to a copy. A concrete
experiment evaluates the installed baseline and the proposed candidate through
the same test harness in separate temporary sandbox runs. Canonical tests are
not replaced by the proposal. An optional generated regression test is supplied
to **both** runs and labeled model-proposed. Code hashes, test hashes, the patch,
and both raw results belong to the archived experiment.

Results distinguish an unchanged regression score, an improvement on the
provided case, a rejected candidate, and an evaluation failure. A green existing
test suite alone does not establish that an agent is smarter, better at new
tasks, or cheaper. Runtime, model-call cost and future task quality need separate
measurements. The patch remains reviewable; an experiment never installs itself
into the running service or changes credentials, identity, tools or permissions.

## Evaluation limits

Tests and summary generation share a Python process with imported candidate
modules. Mark parses the returned summary outside the sandbox, but a candidate
can potentially tamper with unittest or forge its output. Comparing
test identifiers, counts, file hashes and exit status catches ordinary broken
evaluations, but is **not a tamper-proof evaluator**. Treat these results as
regression evidence for reviewing a candidate, not as authorization to deploy.

The generalization check needed for stronger claims is an independent, held-out
set of actual tasks and protected security regressions, evaluated outside the
candidate's control. Repeated optimization on the same tests can overfit.
Untrusted benchmark content can also influence future agent behavior; a recent
research proof of concept includes SICA among the examined systems.
[Benchmark-poisoning study](https://arxiv.org/abs/2609.17817).

Mark's initial extension is a concrete code-edit/evaluate/archive workflow. It is
not a reproduction of SICA's benchmark results, automatic model training, or
automatic production self-replacement.
