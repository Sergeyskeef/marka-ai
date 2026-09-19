"""Reviewable experiments on copies of Mark's own code, inspired by SICA.

An experiment does not install code. Candidate imports share unittest's process,
so the resulting regression signal is not a tamper-proof independent evaluation.
"""
from __future__ import annotations

import ast
import asyncio
import base64
from bisect import bisect_right
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
import zlib

from . import sandbox
from .redact import redact


_MARKER = "MARKA_EVAL_REPORT="
_PROPOSAL_MODULE_BYTES = 60000
_LIMITATION = ("Regression evidence only: imported candidate code shares unittest's process and could "
               "tamper with the evaluator. A model-proposed test is not independent evidence. "
               "No runtime code was installed; this does not establish broader agent improvement.")

# This harness comes from the installed trusted runtime, not from a proposal.
# Keep its stdout short enough to survive the code runner's 32 KB output bound.
_HARNESS = r'''
import base64, contextlib, hashlib, io, json, pathlib, sys, unittest, zlib
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
packed = base64.b64encode(zlib.compress(json.dumps(report, ensure_ascii=False).encode("utf-8"))).decode("ascii")
print("MARKA_EVAL_REPORT=" + json.dumps({"encoding": "zlib-base64", "data": packed}), flush=True)
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

    def _archive_root(self) -> Path:
        root = Path(self.settings.data_dir) / "evolution"
        if root.is_symlink() or (root.exists() and not root.is_dir()):
            raise ValueError("Evolution archive must be a real directory, not a symlink")
        return root

    def _archive_file(self, identifier: str, name: str, maximum: int) -> bytes:
        if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
            raise ValueError("Experiment identifier must be its 32-character lowercase hexadecimal ID")
        root = self._archive_root()
        directory = root / identifier
        path = directory / name
        if (directory.is_symlink() or not directory.is_dir() or path.is_symlink()
                or not path.is_file() or not path.resolve().is_relative_to(root.resolve())):
            raise ValueError("Experiment artifact is missing or has an unsafe archive path")
        if path.stat().st_size > maximum:
            raise ValueError("Experiment artifact exceeds the archive reading limit")
        with path.open("rb") as stream:
            data = stream.read(maximum + 1)
        if len(data) > maximum:
            raise ValueError("Experiment artifact exceeds the archive reading limit")
        return data

    def _read_report(self, identifier: str) -> tuple[dict, bytes]:
        data = self._archive_file(identifier, "report.json", 512 * 1024)
        try:
            report = json.loads(data)
        except (ValueError, UnicodeError):
            raise ValueError("Experiment report is not valid JSON") from None
        statuses = {"evaluation_failed", "rejected", "regression_passed", "improved_on_provided_case"}
        if (not isinstance(report, dict) or report.get("id") != identifier or not isinstance(report.get("status"), str)
                or report["status"] not in statuses
                or report.get("promotion") != "none" or not isinstance(report.get("objective"), str)
                or len(report["objective"]) > 2000 or not isinstance(report.get("created_at"), str)
                or not isinstance(report.get("changed_paths"), list) or not 1 <= len(report["changed_paths"]) <= 3):
            raise ValueError("Experiment report has invalid identity or metadata")
        try:
            created = datetime.fromisoformat(report["created_at"])
        except ValueError:
            raise ValueError("Experiment report has an invalid timestamp") from None
        if created.tzinfo is None or any(not isinstance(path, str) or not re.fullmatch(r"src/marka/[A-Za-z_][A-Za-z0-9_]*\.py", path)
                                          for path in report["changed_paths"]):
            raise ValueError("Experiment report has invalid source paths or timestamp")
        for label in ("baseline", "candidate"):
            hashes = report.get(label + "_hashes")
            if not isinstance(hashes, dict) or not 1 <= len(hashes) <= 1000:
                raise ValueError("Experiment report has no bounded source manifest")
            for path, digest in hashes.items():
                self._source_path(path)
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ValueError("Experiment report contains an invalid source digest")
        return report, data

    @staticmethod
    def _source_path(path: str) -> str:
        sandbox._safe_name(path)
        if not (re.fullmatch(r"src/marka/[A-Za-z_][A-Za-z0-9_]*\.py", path)
                or path in {"src/marka/identity.md", "deploy/guardian.py", "deploy/observer.py", "deploy/marka-observer.service", "deploy/marka-observer.timer"} or (path.startswith("tests/") and path.endswith(".py"))):
            raise ValueError("Only archived public modules, identity and test source may be read")
        return path

    def history(self, limit: int = 8) -> dict:
        if type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError("Experiment history limit must be 1–30")
        root = self._archive_root()
        if not root.exists():
            return {"experiments": [], "skipped_corrupt": 0, "errors": [], "truncated": False,
                    "promotion": "none", "limitation": _LIMITATION}
        candidates, capped = [], False
        with os.scandir(root) as entries:
            for entry in entries:
                if not re.fullmatch(r"[0-9a-f]{32}", entry.name):
                    continue
                if len(candidates) >= 1000:
                    capped = True
                    break
                try:
                    candidates.append((entry.stat(follow_symlinks=False).st_mtime, entry.name))
                except OSError:
                    candidates.append((0, entry.name))
        items, errors, skipped, inspected = [], [], 0, 0
        for _, identifier in sorted(candidates, reverse=True):
            inspected += 1
            try:
                report, data = self._read_report(identifier)
                items.append({"id": identifier, "objective": report["objective"], "status": report["status"],
                              "created_at": report["created_at"], "changed_paths": report["changed_paths"],
                              "reason": str(report.get("reason", ""))[:1000], "report_sha256": _hash(data),
                              "promotion": "none"})
            except (ValueError, OSError):
                skipped += 1
                if len(errors) < 8:
                    errors.append({"id": identifier, "error": "Archive entry is incomplete, corrupt or unsafe"})
            if len(items) >= limit:
                break
        return {"experiments": items, "skipped_corrupt": skipped, "errors": errors,
                "truncated": capped or inspected < len(candidates), "promotion": "none", "limitation": _LIMITATION}

    def read_experiment(self, identifier: str, artifact: str = "report", path: str = "", *,
                        offset: int = 0, limit: int = 8000) -> dict:
        if not isinstance(artifact, str) or artifact not in {"report", "patch", "candidate", "baseline"}:
            raise ValueError("Read report, patch, candidate or baseline")
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 8000:
            raise ValueError("Archive reading requires a nonnegative offset and limit 1–8000")
        if not isinstance(path, str) or (path and artifact in {"report", "patch"}):
            raise ValueError("A source path is supported only for candidate or baseline snapshots")
        report, report_data = self._read_report(identifier)
        meta = {"id": identifier, "artifact": artifact, "status": report["status"], "promotion": "none",
                "report_sha256": _hash(report_data), "trust": "archived_experiment_data", "limitation": _LIMITATION}
        if artifact == "report":
            data = report_data
        elif artifact == "patch":
            data = self._archive_file(identifier, "candidate.patch", 1024 * 1024)
            if report.get("patch_sha256") and report["patch_sha256"] != _hash(data):
                raise ValueError("Experiment patch does not match its recorded digest")
            meta["integrity"] = "matched_report_digest" if report.get("patch_sha256") else "legacy_archive_without_recorded_patch_digest"
        else:
            if path:
                self._source_path(path)
            data = self._archive_file(identifier, artifact + ".json", 4 * 1024 * 1024)
            try:
                sources = json.loads(data)
            except (ValueError, UnicodeError):
                raise ValueError("Experiment source bundle is not valid JSON") from None
            expected = report[artifact + "_hashes"]
            if not isinstance(sources, dict) or set(sources) != set(expected):
                raise ValueError("Experiment source bundle does not match its report manifest")
            for name, text in sources.items():
                if not isinstance(text, str) or _hash(text.encode("utf-8")) != expected[name]:
                    raise ValueError("Experiment source bytes do not match their recorded digest")
            meta["integrity"] = "matched_report_manifest"
            if not path:
                meta.update(manifest_listing=True, total_files=len(sources), bundle_sha256=_hash(data))
                data = _canonical([{"path": name, "sha256": expected[name], "bytes": len(sources[name].encode("utf-8"))}
                                   for name in sorted(sources)])
            else:
                if path not in sources:
                    raise ValueError("Requested source is not part of this experiment")
                meta["path"] = path
                data = sources[path].encode("utf-8")
        try:
            text = data.decode("utf-8")
        except UnicodeError:
            raise ValueError("Experiment artifact is not UTF-8 text") from None
        end = min(len(text), offset + limit)
        return meta | {"content": text[offset:end], "sha256": _hash(data), "offset": offset,
                       "total_chars": len(text), "next_offset": end if end < len(text) else None,
                       "truncated": bool(offset or end < len(text))}

    def _snapshot(self, *, bounded=False) -> dict[str, bytes]:
        files = {}

        def add(name, path):
            if bounded:
                self._source_path(name)
                if len(files) >= 1000 or path.stat().st_size > 524288:
                    raise ValueError("Public source navigation exceeds its file or bundle size limit")
                with path.open("rb") as stream:
                    data = stream.read(524289)
                if len(data) > 524288 or sum(map(len, files.values())) + len(data) > 8 * 1024 * 1024:
                    raise ValueError("Public source navigation exceeds its file or bundle size limit")
            else:
                data = path.read_bytes()
            files[name] = data

        for path in sorted(self.source_root.iterdir()):
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix == ".py" or path.name == "identity.md":
                if bounded and not (re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.py", path.name) or path.name == "identity.md"):
                    continue
                add("src/marka/" + path.name, path)
        if not self.test_root.is_dir():
            raise ValueError("Evaluation tests are unavailable; set MARKA_EVAL_TESTS to the shipped test directory")
        for path in sorted(self.test_root.rglob("*.py")):
            if path.is_symlink() or not path.is_file() or any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(self.test_root).parts):
                continue
            if any(parent.is_symlink() for parent in path.parents if parent != self.test_root and parent.is_relative_to(self.test_root)):
                continue
            add("tests/" + path.relative_to(self.test_root).as_posix(), path)
        if not any(name.startswith("tests/test_") for name in files):
            raise ValueError("No canonical tests were found")
        if "tests/test_model_proposed.py" in files:
            raise ValueError("Canonical tests conflict with the reserved proposed-test filename")
        if not any(name.startswith("src/marka/") for name in files):
            raise ValueError("No installed public source was found")
        for name in ("guardian.py", "observer.py", "marka-observer.service", "marka-observer.timer"):
            helper = self.test_root.parent / "deploy" / name
            if helper.is_file() and not helper.is_symlink() and not helper.parent.is_symlink():
                add("deploy/" + name, helper)
        return files

    def inspect(self, path: str = "", start_line: int = 1, end_line: int = 160, *,
                offset: int | None = None, expected_sha256: str = "") -> dict:
        if not isinstance(path, str):
            raise ValueError("Source path must be a string")
        if (type(start_line) is not int or type(end_line) is not int or start_line < 1
                or end_line < start_line or end_line - start_line > 199):
            raise ValueError("Inspect 1–200 source lines per page")
        if offset is not None and (type(offset) is not int or offset < 0):
            raise ValueError("Source offset must be a nonnegative character position")
        if not isinstance(expected_sha256, str) or (expected_sha256 and not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)):
            raise ValueError("Expected source hash must be lowercase SHA256")
        if not path and (offset is not None or expected_sha256):
            raise ValueError("Source pagination and hash checks require a path")
        if path:
            self._source_path(path)
        files = self._snapshot(bounded=True)
        if not path:
            return {"files": [{"path": name, "bytes": len(data), "sha256": _hash(data),
                               **self._change_size_metadata(data)}
                              for name, data in sorted(files.items())],
                    "editable": "src/marka/*.py; at most 3 files per experiment",
                    "self_change_proposal_limit_bytes": _PROPOSAL_MODULE_BYTES,
                    "canonical_tests_editable": False, "promotion": "none",
                    "limitation": _LIMITATION}
        if path not in files:
            raise ValueError("Only installed public source and shipped test files can be inspected")
        text = files[path].decode("utf-8")
        digest = _hash(files[path])
        if expected_sha256 and expected_sha256 != digest:
            raise ValueError("Installed source changed; restart reading with its current hash")
        lines = text.splitlines(keepends=True)
        starts, position = [], 0
        for line in lines:
            starts.append(position)
            position += len(line)
        if offset is None:
            begin = starts[start_line - 1] if start_line <= len(starts) else len(text)
            requested_end = starts[end_line] if end_line < len(starts) else len(text)
            end = min(requested_end, begin + 12000)
        else:
            begin = min(offset, len(text))
            end = min(len(text), begin + 12000)
        return {"path": path, "content": text[begin:end], "sha256": digest, **self._change_size_metadata(files[path]),
                "start_line": bisect_right(starts, begin) if end > begin else None,
                "end_line": bisect_right(starts, end - 1) if end > begin else None,
                "total_lines": len(lines), "offset": begin, "next_offset": end if end < len(text) else None,
                "total_chars": len(text), "truncated": bool(begin or end < len(text))}

    @staticmethod
    def _change_size_metadata(data: bytes) -> dict:
        eligible = len(data) <= _PROPOSAL_MODULE_BYTES
        return {"self_change_proposal_limit_bytes": _PROPOSAL_MODULE_BYTES,
                "self_change_size_eligible": eligible,
                "self_change_size_reason": None if eligible else "current_file_exceeds_proposal_limit",
                "self_change_size_note": ("Size check only; source-path and independent promotion checks still apply."
                                          if eligible else
                                          "Current file exceeds the 60000-byte proposal limit. A smaller proposed module may fit; "
                                          "changes retaining this size require an operator release.")}

    def search(self, query: str, path: str = "", limit: int = 20) -> dict:
        """Find literal text only in the installed public source snapshot."""
        if not isinstance(query, str) or not 1 <= len(query) <= 200 or not query.strip() or any(ch in query for ch in "\r\n\x00"):
            raise ValueError("Source search needs 1–200 characters of literal single-line text")
        if not isinstance(path, str) or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("Source search requires a public path and a limit of 1–50")
        if path:
            self._source_path(path)
        files = self._snapshot(bounded=True)
        if path and path not in files:
            raise ValueError("Only installed public source and shipped test files can be searched")
        matches, searched, truncated = [], 0, False
        for name, data in sorted(files.items()):
            if path and name != path:
                continue
            text = data.decode("utf-8")
            digest, position = _hash(data), 0
            searched += 1
            for number, line in enumerate(text.splitlines(keepends=True), 1):
                cursor = 0
                while (found := line.find(query, cursor)) >= 0:
                    if len(matches) >= limit:
                        truncated = True
                        break
                    excerpt_begin = max(0, found - 40)
                    excerpt_end = min(len(line), excerpt_begin + 240)
                    matches.append({"path": name, "line": number, "column": found + 1,
                                    "offset": position + found, "end_offset": position + found + len(query),
                                    "sha256": digest, "excerpt": line[excerpt_begin:excerpt_end],
                                    "excerpt_offset": position + excerpt_begin,
                                    "excerpt_truncated": bool(excerpt_begin or excerpt_end < len(line))})
                    cursor = found + len(query)
                if truncated:
                    break
                position += len(line)
            if truncated:
                break
        return {"query": query, "matches": matches, "limit": limit, "truncated": truncated,
                "files_searched": searched, "literal": True, "case_sensitive": True}

    @staticmethod
    def _changes(changes: dict[str, str]) -> dict[str, bytes]:
        if not isinstance(changes, dict) or not 1 <= len(changes) <= 3:
            raise ValueError("An experiment needs 1–3 changed Python modules")
        result = {}
        for name, text in changes.items():
            if not isinstance(name, str) or not re.fullmatch(r"src/marka/[A-Za-z_][A-Za-z0-9_]*\.py", name):
                raise ValueError("Only src/marka/*.py candidate modules may change")
            if not isinstance(text, str) or len(text.encode("utf-8")) > _PROPOSAL_MODULE_BYTES:
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
            if isinstance(report, dict) and report.get("encoding") == "zlib-base64":
                data = report.get("data")
                if not isinstance(data, str) or len(data) > 50000:
                    raise ValueError("Invalid compressed evaluation report")
                packed = base64.b64decode(data, validate=True)
                decoder = zlib.decompressobj()
                unpacked = decoder.decompress(packed, 262145)
                if len(unpacked) > 262144 or not decoder.eof or decoder.unused_data:
                    raise ValueError("Evaluation report exceeds its bounded decoded size")
                report = json.loads(unpacked)
        except (ValueError, zlib.error, UnicodeError):
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
                    "tests": {name: _hash(data) for name, data in files.items() if name.startswith(("tests/", "deploy/"))}}
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
                  "patch_sha256": _hash(patch_text.encode("utf-8")),
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
