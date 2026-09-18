"""Reviewable experiments on copies of Mark's own code, inspired by SICA.

An experiment does not install code. Candidate imports share unittest's process,
so the resulting regression signal is not a tamper-proof independent evaluation.
"""
from __future__ import annotations

import ast
import asyncio
import base64
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from . import sandbox
from .redact import redact


_MARKER = "MARKA_EVAL_REPORT="
_LIMITATION = ("Regression evidence only: imported candidate code shares unittest's process and could "
               "tamper with the evaluator. A model-proposed test is not independent evidence. "
               "No runtime code was installed; this does not establish broader agent improvement.")

# This harness comes from the installed trusted runtime, not from a proposal.
# Keep its stdout short enough to survive the code runner's 32 KB output bound.
_HARNESS = r'''
import contextlib, hashlib, io, json, pathlib, sys, unittest
root = pathlib.Path.cwd()
manifest = json.loads((root / "eval_manifest.json").read_text("utf-8"))
sys.path.insert(0, str(root / "src"))
def intact(expected):
    return all((root / name).is_file() and hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
               for name, digest in expected.items())
class BoundedOutput(io.TextIOBase):
    def __init__(self): self.parts, self.size = [], 0
    def write(self, value):
        remaining = max(0, 2000 - self.size)
        self.parts.append(value[:remaining]); self.size += min(len(value), remaining)
        return len(value)
    def flush(self): pass
    def text(self): return "".join(self.parts)
def identifiers(suite):
    result = []
    for item in suite:
        result.extend(identifiers(item) if isinstance(item, unittest.TestSuite) else [item.id()])
    return result
class Results(unittest.TestResult):
    def __init__(self): super().__init__(); self.outcomes = {}
    def addSuccess(self, test): super().addSuccess(test); self.outcomes[test.id()] = "passed"
    def addFailure(self, test, err): super().addFailure(test, err); self.outcomes[test.id()] = "failed"
    def addError(self, test, err): super().addError(test, err); self.outcomes[test.id()] = "error"
    def addSkip(self, test, reason): super().addSkip(test, reason); self.outcomes[test.id()] = "skipped"
    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err); self.outcomes[test.id()] = "expected_failure"
    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test); self.outcomes[test.id()] = "unexpected_success"
    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None: self.outcomes[test.id()] = "failed"
capture = BoundedOutput()
before = intact(manifest["tests"]) and intact(manifest["sources"])
with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
    suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py")
    discovered = identifiers(suite)
    results = Results()
    suite.run(results)
report = {"nonce": manifest["nonce"], "discovered_count": len(discovered),
          "discovered_sha256": hashlib.sha256(json.dumps(sorted(discovered), ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(),
          "tests_run": results.testsRun, "outcomes": results.outcomes,
          "test_integrity": before and intact(manifest["tests"]),
          "source_integrity": before and intact(manifest["sources"]),
          "successful": results.wasSuccessful(), "log": capture.text(),
          "failures": [{"id": test.id(), "traceback": text[-600:]}
                       for test, text in (results.failures + results.errors)[:4]]}
print("MARKA_EVAL_REPORT=" + json.dumps(report, ensure_ascii=False), flush=True)
sys.exit(0 if results.wasSuccessful() else 1)
'''


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


class Evolution:
    def __init__(self, settings, workspace, *, source_root: Path | None = None,
                 test_root: Path | None = None, runner=None):
        self.settings, self.workspace = settings, workspace
        self.source_root = Path(source_root or Path(__file__).parent).resolve()
        default_tests = self.source_root.parent.parent / "tests"
        self.test_root = Path(test_root or os.environ.get("MARKA_EVAL_TESTS", default_tests)).resolve()
        self.runner = runner or sandbox.run_client

    def _snapshot(self) -> dict[str, bytes]:
        files = {}
        for path in sorted(self.source_root.iterdir()):
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix == ".py" or path.name == "identity.md":
                files["src/marka/" + path.name] = path.read_bytes()
        if not self.test_root.is_dir():
            raise ValueError("Evaluation tests are unavailable; set MARKA_EVAL_TESTS to the shipped test directory")
        for path in sorted(self.test_root.rglob("*.py")):
            if path.is_symlink() or any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(self.test_root).parts):
                continue
            if any(parent.is_symlink() for parent in path.parents if parent != self.test_root and parent.is_relative_to(self.test_root)):
                continue
            files["tests/" + path.relative_to(self.test_root).as_posix()] = path.read_bytes()
        if not any(name.startswith("tests/test_") for name in files):
            raise ValueError("No canonical tests were found")
        if "tests/test_model_proposed.py" in files:
            raise ValueError("Canonical tests conflict with the reserved proposed-test filename")
        if not any(name.startswith("src/marka/") for name in files):
            raise ValueError("No installed public source was found")
        return files

    def inspect(self, path: str = "") -> dict:
        files = self._snapshot()
        if not path:
            return {"files": [{"path": name, "bytes": len(data), "sha256": _hash(data)}
                              for name, data in sorted(files.items())],
                    "editable": "src/marka/*.py; at most 3 files per experiment",
                    "canonical_tests_editable": False, "promotion": "none",
                    "limitation": _LIMITATION}
        if path not in files:
            raise ValueError("Only installed public source and shipped test files can be inspected")
        text = files[path].decode("utf-8")
        return {"path": path, "content": text[:60000], "truncated": len(text) > 60000,
                "sha256": _hash(files[path])}

    @staticmethod
    def _changes(changes: dict[str, str]) -> dict[str, bytes]:
        if not isinstance(changes, dict) or not 1 <= len(changes) <= 3:
            raise ValueError("An experiment needs 1–3 changed Python modules")
        result = {}
        for name, text in changes.items():
            if not isinstance(name, str) or not re.fullmatch(r"src/marka/[A-Za-z_][A-Za-z0-9_]*\.py", name):
                raise ValueError("Only src/marka/*.py candidate modules may change")
            if not isinstance(text, str) or len(text.encode("utf-8")) > 60000:
                raise ValueError("Each changed module must contain at most 60000 UTF-8 bytes")
            try:
                ast.parse(text, filename=name)
            except SyntaxError as exc:
                raise ValueError(f"Invalid candidate Python syntax in {name}, line {exc.lineno}") from None
            result[name] = text.encode("utf-8")
        return result

    @staticmethod
    def _parse(result: dict, nonce: str) -> dict:
        if not isinstance(result, dict) or result.get("timed_out") or result.get("error") or result.get("truncated"):
            raise ValueError("Sandbox evaluation did not finish with a complete result")
        lines = [line[len(_MARKER):] for line in str(result.get("output", "")).splitlines() if line.startswith(_MARKER)]
        if len(lines) != 1:
            raise ValueError("Evaluation requires exactly one structured summary")
        try:
            report = json.loads(lines[0])
        except json.JSONDecodeError:
            raise ValueError("Evaluation summary is not valid JSON") from None
        if not isinstance(report, dict) or report.get("nonce") != nonce:
            raise ValueError("Evaluation summary does not match the run")
        outcomes = report.get("outcomes")
        if (not isinstance(outcomes, dict) or not outcomes or len(outcomes) > 1000
                or not all(isinstance(item, str) for item in outcomes)
                or type(report.get("tests_run")) is not int or report["tests_run"] != len(outcomes)
                or type(report.get("discovered_count")) is not int or report["discovered_count"] != len(outcomes)
                or report.get("discovered_sha256") != _hash(_canonical(sorted(outcomes)))):
            raise ValueError("Evaluation did not execute every discovered test exactly once")
        if any("_FailedTest" in name for name in outcomes):
            raise ValueError("Test discovery failed")
        allowed = {"passed", "failed", "error", "skipped", "expected_failure", "unexpected_success"}
        if not all(value in allowed for value in outcomes.values()):
            raise ValueError("Evaluation contains an unknown test outcome")
        if all(value == "skipped" for value in outcomes.values()):
            raise ValueError("Evaluation skipped every test")
        if report.get("test_integrity") is not True or report.get("source_integrity") is not True:
            raise ValueError("Evaluation changed canonical tests or source snapshots")
        successful = all(value in {"passed", "skipped", "expected_failure"} for value in outcomes.values())
        if report.get("successful") is not successful or result.get("exit_code") != (0 if successful else 1):
            raise ValueError("Test outcomes disagree with process exit status")
        return report

    @staticmethod
    def _compare(baseline: dict, candidate: dict) -> tuple[str, list[str], str]:
        old, new = baseline["outcomes"], candidate["outcomes"]
        if set(old) != set(new):
            return "evaluation_failed", [], "Baseline and candidate discovered different test identifiers"
        if any(value in {"skipped", "expected_failure"} and value != old[name] for name, value in new.items()):
            return "rejected", [], "Candidate skipped or weakened a previously executed test"
        if any(value in {"failed", "error", "unexpected_success"} for value in new.values()):
            return "rejected", [], "Candidate has failing tests"
        improved = [name for name in sorted(old) if old[name] in {"failed", "error"} and new[name] == "passed"]
        if improved:
            return "improved_on_provided_case", improved, "Previously failing provided cases passed; generalization is unmeasured"
        return "regression_passed", [], "Candidate passed the same regression suite; a broader improvement is unmeasured"

    async def _evaluate(self, files: dict[str, bytes], nonce: str) -> dict:
        manifest = {"nonce": nonce,
                    "sources": {name: _hash(data) for name, data in files.items() if name.startswith("src/")},
                    "tests": {name: _hash(data) for name, data in files.items() if name.startswith("tests/")}}
        payload = files | {"eval_runner.py": _HARNESS.encode("utf-8"), "eval_manifest.json": _canonical(manifest)}
        encoded = {name: base64.b64encode(data).decode("ascii") for name, data in payload.items()}
        sandbox._decode_files(encoded)  # Validate the exact shared runner size/path contract first.
        raw = await asyncio.to_thread(self.runner, self.settings.sandbox_socket,
                                      ["python", "eval_runner.py"], 60, encoded)
        return raw

    async def experiment(self, objective: str, changes: dict[str, str], regression_test: str = "") -> dict:
        if not isinstance(objective, str) or not objective.strip() or len(objective) > 2000:
            raise ValueError("Provide a concrete objective of 1–2000 characters")
        edits = self._changes(changes)
        baseline_files = self._snapshot()
        if all(baseline_files.get(name) == data for name, data in edits.items()):
            raise ValueError("Candidate must change the installed source")
        if not isinstance(regression_test, str) or len(regression_test.encode("utf-8")) > 30000:
            raise ValueError("Proposed regression test exceeds 30000 UTF-8 bytes")
        if regression_test.strip():
            try:
                ast.parse(regression_test, filename="test_model_proposed.py")
            except SyntaxError as exc:
                raise ValueError(f"Invalid proposed test syntax, line {exc.lineno}") from None
            baseline_files["tests/test_model_proposed.py"] = regression_test.encode("utf-8")
        candidate_files = baseline_files | edits
        identifier = uuid.uuid4().hex
        parent = Path(self.settings.data_dir) / "evolution"
        if parent.is_symlink():
            raise ValueError("Evolution archive must not be a symlink")
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        archive = parent / identifier
        archive.mkdir(mode=0o700)
        patch_lines = []
        for name, content in sorted(edits.items()):
            for line in difflib.unified_diff(
                baseline_files.get(name, b"").decode("utf-8").splitlines(keepends=True),
                content.decode("utf-8").splitlines(keepends=True),
                fromfile="a/" + name, tofile="b/" + name,
            ):
                patch_lines.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
        patch_text = "".join(patch_lines)

        def save(name: str, value: bytes):
            descriptor = os.open(archive / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())

        baseline_hashes = {name: _hash(data) for name, data in baseline_files.items()}
        candidate_hashes = {name: _hash(data) for name, data in candidate_files.items()}
        tests_hash = _hash(_canonical({name: digest for name, digest in baseline_hashes.items() if name.startswith("tests/")}))
        save("baseline.json", _canonical({name: data.decode("utf-8") for name, data in baseline_files.items()}))
        save("candidate.json", _canonical({name: data.decode("utf-8") for name, data in candidate_files.items()}))
        save("candidate.patch", patch_text.encode("utf-8"))
        report = {"id": identifier, "objective": redact(objective), "status": "evaluation_failed",
                  "created_at": datetime.now(timezone.utc).isoformat(), "changed_paths": sorted(edits),
                  "baseline_hashes": baseline_hashes, "candidate_hashes": candidate_hashes,
                  "tests_sha256": tests_hash, "harness_sha256": _hash(_HARNESS.encode("utf-8")),
                  "model_proposed_test": bool(regression_test.strip()), "promotion": "none",
                  "limitation": _LIMITATION, "baseline": None, "candidate": None, "improved_tests": []}
        try:
            if not self.settings.sandbox_socket:
                raise ValueError("Code runner is required to evaluate a candidate; ordinary host execution is disabled")
            for label, files in (("baseline", baseline_files), ("candidate", candidate_files)):
                nonce = uuid.uuid4().hex
                # Save the nonce and exact input identity before a potentially interrupted run.
                save(label + "-run.json", _canonical({"nonce": nonce, "file_hashes": baseline_hashes if label == "baseline" else candidate_hashes}))
                raw = await self._evaluate(files, nonce)
                save(label + "-result.json", _canonical(raw))
                report[label] = self._parse(raw, nonce)
            report["status"], report["improved_tests"], report["reason"] = self._compare(report["baseline"], report["candidate"])
        except (ValueError, OSError, KeyError, TypeError) as exc:
            report["reason"] = redact(str(exc))[:1000] if isinstance(exc, ValueError) else "Evaluation failed: " + type(exc).__name__
        save("report.json", _canonical(report))
        text = (f"# Mark code experiment {identifier}\n\n"
                f"Objective: {report['objective']}\n\nResult: **{report['status']}**\n\n{report.get('reason', '')}\n\n"
                f"Changes: {', '.join(report['changed_paths'])}\n\n"
                f"Test bundle SHA256: `{tests_hash}`\n\n"
                f"Generated regression test: {'model-proposed, included in both runs' if report['model_proposed_test'] else 'none'}\n\n"
                f"Improved provided cases: {', '.join(report['improved_tests']) or 'none'}\n\n"
                f"{_LIMITATION}\n\nRuntime installation: **none**. Review the patch and full private experiment archive before any deployment.\n")
        save("report.md", text.encode("utf-8"))
        # The archive interface is append-only: future experiments receive a new UUID.
        for path in archive.iterdir():
            path.chmod(0o400)
        report_path, patch_path = f"evolution/{identifier}/report.md", f"evolution/{identifier}/candidate.patch"
        self.workspace.write_bytes(report_path, text.encode("utf-8"))
        self.workspace.write_bytes(patch_path, patch_text.encode("utf-8"))
        return {"id": identifier, "status": report["status"], "reason": report.get("reason"),
                "report_path": report_path, "patch_path": patch_path,
                "baseline_tests": report["baseline"]["tests_run"] if report["baseline"] else None,
                "candidate_tests": report["candidate"]["tests_run"] if report["candidate"] else None,
                "improved_tests": report["improved_tests"], "promotion": "none", "limitation": _LIMITATION}
