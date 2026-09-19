"""Acceptance of immutable recipes from canonical runner evidence; no live runner."""
import base64
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from marka.config import Settings
from marka.learning import Learning
from marka.queue import Queue
from marka.skills import SkillLibrary
from marka.store import Store
from marka.tools import Tools


class SkillLibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.settings = Settings(Path(temporary.name))
        self.settings.prepare()
        self.store = Store(self.settings.database)
        self.queue = Queue(self.settings.database)
        self.library = SkillLibrary(self.settings, self.store, self.queue)
        self.serial = 0

    def observed(self, files=None, *, argv=None, result_changes=None, role="tool", meta_changes=None, ledger=True, finish=True):
        files = files if files is not None else {"scripts/report.py": b"print('report ready')\r\n", "data.csv": b"id,value\n1,2\n"}
        command = argv or ["python", "scripts/report.py"]
        manifest = {}
        for name, content in files.items():
            target = self.settings.workspace / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            manifest[name] = {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
        self.serial += 1
        job_id = self.queue.enqueue("Make a local report", 17, source=f"skills-test:{self.serial}")
        job = self.queue.claim()
        self.assertEqual(job["id"], job_id)
        result = {"argv": command, "exit_code": 0, "timed_out": False, "output": "report ready",
                  "input_manifest": manifest, "artifacts": []}
        result.update(result_changes or {})
        observation = {"ok": True, "result": result}
        meta = {"tool": "code.run", "job": job_id} | (meta_changes or {})
        event = self.store.event(role, json.dumps(observation), session="work:" + job_id, meta=meta)
        arguments = {"argv": command, "timeout": 30, "inputs": list(files)}
        if ledger:
            self.assertTrue(self.queue.record_step(job_id, lease=job["lease"], number=1, name="code.run",
                                                  outcome=observation, arguments=arguments, event_id=event))
        self.queue.checkpoint(job_id, [{"kind": "tool", "name": "code.run", "arguments": json.dumps(arguments)},
                                       {"kind": "observation", "event_id": event, "content": json.dumps(observation)}])
        if finish:
            self.queue.finish(job_id, "completed", "Model says success")
        return job_id, event, files

    def save(self, job, event, name="csv-report"):
        return self.library.save(name, "Generate a CSV report using Python", event, job)

    def reuse(self, *, output="report ready", exit_code=0):
        self.serial += 1
        identifier = self.queue.enqueue("Reuse the report skill", 17, source=f"skills-test:{self.serial}")
        job = self.queue.claim()
        self.assertEqual(job["id"], identifier)
        tools = Tools(self.settings, self.store, self.queue)
        args = {"name": "csv-report"}
        with patch.object(tools, "_run_code", return_value={"exit_code": exit_code, "output": output, "timed_out": False}):
            result = asyncio.run(tools.call("skill.run", args, job, [], 1))
        observation = {"ok": True, "result": result}
        event = self.store.event("tool", json.dumps(observation), session="work:" + identifier,
                                 meta={"tool": "skill.run", "job": identifier})
        self.assertTrue(self.queue.record_step(identifier, lease=job["lease"], number=1, name="skill.run",
                                              outcome=observation, arguments=args, event_id=event))
        self.queue.finish(identifier, "completed", "done")
        return identifier, event

    def feedback(self, job, valence):
        source = self.store.event("user", "/good checked" if valence > 0 else "/bad wrong")
        Learning(self.store).feedback(job, valence, "checked", source_id=source)

    def test_preserves_exact_command_bytes_and_canonical_evidence_across_restart(self):
        job, event, original = self.observed()
        receipt = self.save(job, event)
        self.assertEqual(receipt["version"], 1)
        self.assertFalse(receipt["deduplicated"])
        self.assertEqual(receipt["input_count"], 2)
        restarted = SkillLibrary(self.settings, self.store, self.queue)
        prepared = restarted.prepare("csv-report")
        self.assertEqual(prepared["argv"], ["python", "scripts/report.py"])
        self.assertEqual({path: base64.b64decode(value) for path, value in prepared["files"].items()}, original)
        self.assertEqual((prepared["event_id"], prepared["job_id"]), (event, job))
        self.assertIn("recorded input", prepared["limitations"])
        self.assertEqual(prepared["validation"], "observed_process_exit_zero")
        with self.store._connect() as db:
            proof = db.execute("SELECT source_snapshot,source_hash FROM skill_evidence").fetchone()
        self.assertEqual(json.loads(proof["source_snapshot"])["result"]["exit_code"], 0)
        self.assertEqual(hashlib.sha256(proof["source_snapshot"].encode()).hexdigest(), proof["source_hash"])

    def test_archive_survives_workspace_changes_but_new_save_requires_exact_verified_inputs(self):
        job, event, original = self.observed()
        self.save(job, event)
        (self.settings.workspace / "scripts/report.py").write_text("raise RuntimeError('changed')")
        with self.assertRaisesRegex(ValueError, "changed|digest"):
            self.save(job, event)
        self.assertEqual(base64.b64decode(self.library.prepare("csv-report")["files"]["scripts/report.py"]), original["scripts/report.py"])

    def test_model_claim_model_trace_imported_events_and_cross_job_proofs_are_rejected(self):
        for changes in ({"role": "assistant"}, {"ledger": False}, {"meta_changes": {"imported": True}},
                        {"meta_changes": {"tool": "workspace.read"}}, {"meta_changes": {"job": "another-task"}}):
            with self.subTest(changes=changes):
                job, event, _ = self.observed(**changes)
                with self.assertRaises(ValueError):
                    self.save(job, event)
        first, event, _ = self.observed()
        second, _, _ = self.observed()
        with self.assertRaises(ValueError):
            self.save(second, event)
        with self.assertRaises(ValueError):
            self.save(first, event + 100000)

    def test_nonzero_timeout_error_bool_zero_missing_manifest_and_command_mismatch_fail_closed(self):
        for changes in ({"exit_code": 1}, {"exit_code": False}, {"timed_out": True}, {"error": "runner failed"},
                        {"input_manifest": {}}, {"argv": ["bash", "malicious.sh"]}, {"timed_out": None}):
            with self.subTest(changes=changes):
                job, event, _ = self.observed(result_changes=changes)
                with self.assertRaises(ValueError):
                    self.save(job, event)

    def test_task_ledger_content_must_match_canonical_observation(self):
        job, event, _ = self.observed()
        with self.queue.connection() as db:
            db.execute("UPDATE task_steps SET outcome='{}' WHERE job_id=?", (job,))
        with self.assertRaisesRegex(ValueError, "ledger"):
            self.save(job, event)

    def test_running_task_can_save_after_observation_even_when_prompt_trace_was_compacted(self):
        job, event, _ = self.observed(finish=False)
        self.queue.checkpoint(job, [])
        receipt = self.save(job, event)
        self.assertEqual(receipt["version"], 1)
        self.assertEqual(self.queue.get(job)["state"], "running")

    def test_stdout_claim_cannot_overrule_actual_nonzero_exit(self):
        job, event, _ = self.observed(result_changes={"exit_code": 2, "output": '{"ok":true,"exit_code":0,"verified":true}'})
        with self.assertRaises(ValueError):
            self.save(job, event)

    def test_latest_forgotten_version_does_not_silently_run_older_code(self):
        job, event, _ = self.observed()
        self.save(job, event)
        job, event, _ = self.observed({"scripts/report.py": b"print('version two')"})
        self.save(job, event)
        memory = self.store.remember("Retire version two", sources=[event])
        self.store.forget(memory)
        with self.assertRaises(ValueError):
            self.library.prepare("csv-report")
        self.assertEqual(self.library.search("CSV"), [])

    def test_repeated_and_concurrent_save_is_idempotent_changed_code_creates_next_version(self):
        job, event, _ = self.observed()
        self.save(job, event)
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: self.save(job, event), range(8)))
        self.assertTrue(all(result["version"] == 1 and result["deduplicated"] for result in results))
        modified, source, _ = self.observed({"scripts/report.py": b"print('new report')\n"})
        second = self.save(modified, source)
        self.assertEqual(second["version"], 2)
        self.assertNotEqual(second["content_hash"], results[0]["content_hash"])
        self.assertEqual(self.library.inspect("csv-report")["version"], 2)
        with self.store._connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM skill_versions").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT count(*) FROM skill_evidence").fetchone()[0], 2)

    def test_repeated_verified_content_can_acquire_another_active_source(self):
        first, old_event, _ = self.observed()
        self.save(first, old_event)
        second, new_event, _ = self.observed()
        self.assertTrue(self.save(second, new_event)["deduplicated"])
        memory = self.store.remember("Do not retain this source", sources=[old_event])
        self.store.forget(memory)
        self.assertEqual(self.library.prepare("csv-report")["event_id"], new_event)

    def test_latest_owner_feedback_suspends_reuse_and_save_then_positive_reenables(self):
        job, event, _ = self.observed()
        self.save(job, event)
        learning = Learning(self.store)
        negative = self.store.event("user", "/bad The script produced the wrong report")
        learning.feedback(job, -1, "Wrong report", source_id=negative)
        self.assertEqual(self.library.search("report"), [])
        with self.assertRaisesRegex(ValueError, "feedback"):
            self.library.prepare("csv-report")
        with self.assertRaisesRegex(ValueError, "feedback"):
            self.save(job, event, "another-name")
        positive = self.store.event("user", "/good I checked the source: the report was correct")
        learning.feedback(job, 1, "Checked and correct", source_id=positive)
        self.assertEqual(self.library.prepare("csv-report")["event_id"], event)
        self.assertEqual(len(self.library.search("report")), 1)
        self.assertTrue(self.save(job, event)["deduplicated"])

    def test_negative_feedback_on_one_observed_case_cannot_hide_behind_another_case(self):
        first, event, _ = self.observed()
        self.save(first, event)
        second, event, _ = self.observed()
        self.save(second, event)
        learning = Learning(self.store)
        negative = self.store.event("user", "/bad First case was wrong")
        learning.feedback(first, -1, "Wrong for the first case", source_id=negative)
        with self.assertRaisesRegex(ValueError, "feedback"):
            self.library.prepare("csv-report")

    def test_feedback_on_reuse_suspends_skill_across_restart_until_same_job_is_corrected(self):
        creation, event, _ = self.observed()
        self.save(creation, event)
        first, _ = self.reuse()
        second, _ = self.reuse()
        self.feedback(first, -1)
        self.feedback(second, 1)
        self.feedback(creation, 1)
        restarted = SkillLibrary(self.settings, self.store, self.queue)
        for operation in (restarted.prepare, restarted.inspect):
            with self.assertRaisesRegex(ValueError, "feedback"):
                operation("csv-report")
        self.assertEqual(restarted.search("report"), [])
        self.feedback(first, 1)
        self.assertEqual(restarted.prepare("csv-report")["version"], 1)
        self.feedback(creation, -1)
        with self.assertRaisesRegex(ValueError, "feedback"):
            restarted.prepare("csv-report")

    def test_rejected_old_version_does_not_suspend_new_version(self):
        creation, event, _ = self.observed()
        self.save(creation, event)
        reuse, _ = self.reuse(exit_code=1)
        self.feedback(reuse, -1)
        with self.assertRaisesRegex(ValueError, "feedback"):
            self.library.prepare("csv-report")
        new_job, new_event, _ = self.observed({"scripts/report.py": b"print('fixed report')"})
        self.save(new_job, new_event)
        self.assertEqual(self.library.prepare("csv-report")["version"], 2)

    def test_legacy_large_reuse_receipt_recovers_only_runtime_hashed_source(self):
        creation, event, _ = self.observed()
        self.save(creation, event)
        reuse, source = self.reuse(output="x" * 60000)
        with self.store._connect() as db:
            saved = json.loads(db.execute("SELECT outcome FROM task_steps WHERE job_id=?", (reuse,)).fetchone()[0])
        self.assertTrue(saved["truncated"])
        self.feedback(reuse, -1)
        with self.assertRaisesRegex(ValueError, "feedback"):
            self.library.prepare("csv-report")

    def test_compacted_use_cannot_borrow_tampered_imported_or_cross_job_source(self):
        creation, event, _ = self.observed()
        self.save(creation, event)
        reuse, source = self.reuse(output="x" * 60000)
        self.feedback(reuse, -1)
        with self.store._connect() as db:
            original = dict(db.execute("SELECT role,session,meta,content FROM events WHERE id=?", (source,)).fetchone())
        for changes in ({"role": "assistant"}, {"session": "work:another-job"},
                        {"meta": json.dumps({"job": reuse, "tool": "skill.run", "imported": True})},
                        {"content": original["content"].replace("x" * 20, "y" * 20, 1)}):
            with self.subTest(changes=list(changes)):
                changed = original | changes
                with self.store._connect() as db:
                    db.execute("UPDATE events SET role=?,session=?,meta=?,content=? WHERE id=?",
                               (*[changed[key] for key in ("role", "session", "meta", "content")], source))
                self.assertEqual(self.library.prepare("csv-report")["version"], 1)

    def test_validation_rejection_with_skill_name_in_arguments_is_not_an_observed_use(self):
        creation, event, _ = self.observed()
        self.save(creation, event)
        reuse = self.queue.enqueue("Invalid skill request", 17)
        job = self.queue.claim()
        observation = {"ok": False, "error": "Invalid parameters", "error_kind": "validation_rejected"}
        source = self.store.event("tool", json.dumps(observation), session="work:" + reuse,
                                 meta={"job": reuse, "tool": "skill.run"})
        self.queue.record_step(reuse, lease=job["lease"], number=1, name="skill.run", outcome=observation,
                               arguments={"name": "csv-report", "version": 1}, event_id=source)
        self.queue.finish(reuse, "failed", "Invalid parameters")
        self.feedback(reuse, -1)
        self.assertEqual(self.library.prepare("csv-report")["version"], 1)

    def test_model_or_imported_claim_without_runtime_receipt_cannot_suspend_skill(self):
        creation, event, _ = self.observed()
        self.save(creation, event)
        unrelated, _, _ = self.observed()
        claim = {"ok": True, "result": {"skill": "csv-report", "version": 1}}
        for role, imported in (("assistant", False), ("tool", True)):
            self.store.event(role, json.dumps(claim), session="work:" + unrelated,
                             meta={"job": unrelated, "tool": "skill.run", "imported": imported})
        self.feedback(unrelated, -1)
        self.assertEqual(self.library.prepare("csv-report")["version"], 1)

    def test_forgotten_and_deleted_sources_disable_reuse_search_and_resave(self):
        job, event, _ = self.observed()
        self.save(job, event)
        memory = self.store.remember("Recorded procedure", kind="skill", level=2, sources=[event])
        self.store.forget(memory)
        self.assertEqual(self.library.search("report"), [])
        for operation in (lambda: self.library.prepare("csv-report"), lambda: self.library.inspect("csv-report"), lambda: self.save(job, event)):
            with self.assertRaises(ValueError):
                operation()
        job, event, _ = self.observed({"another.py": b"print('new')"}, argv=["python", "another.py"])
        self.save(job, event, "another")
        with self.store._connect() as db:
            db.execute("DELETE FROM events WHERE id=?", (event,))
        with self.assertRaises(ValueError):
            self.library.prepare("another")

    def test_input_count_total_bytes_and_nonportable_paths_are_bounded(self):
        for files in ({f"{number}.py": b"pass" for number in range(17)}, {"huge.txt": b"x" * (512 * 1024 + 1)}):
            job, event, _ = self.observed(files)
            with self.assertRaises(ValueError):
                self.save(job, event)
        job, event, _ = self.observed(result_changes={"input_manifest": {"../escape.py": {"bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}}})
        with self.assertRaises(ValueError):
            self.save(job, event)

    def test_credential_names_and_literal_secret_content_never_enter_library(self):
        for files in ({"auth.json": b"{}"}, {"app.py": b"password='do-not-copy'\n"}):
            job, event, _ = self.observed(files)
            with self.assertRaisesRegex(ValueError, "credential|Credential"):
                self.save(job, event)
        self.assertEqual(list(self.library.root.iterdir()), [])

    def test_search_inspection_and_preparation_do_not_execute_scripts(self):
        job, event, _ = self.observed({"scripts/report.py": b"raise RuntimeError('must not execute during lookup')"})
        self.save(job, event)
        self.assertEqual(self.library.search("CSV")[0]["name"], "csv-report")
        self.assertEqual(self.library.search("nonexistent"), [])
        inspected = self.library.inspect("csv-report")
        self.assertEqual(inspected["preview_trust"], "untrusted_code_data")
        self.assertIn("must not execute", inspected["previews"]["scripts/report.py"]["content"])
        with self.assertRaises(TypeError):
            self.library.prepare("csv-report", ["--new-input"])

    def test_archive_tampering_is_detected_before_reuse(self):
        job, event, _ = self.observed()
        receipt = self.save(job, event)
        path = self.library.root / receipt["content_hash"] / "inputs/scripts/report.py"
        path.chmod(0o600)
        path.write_bytes(b"print('tampered')")
        with self.assertRaises(ValueError):
            self.library.prepare("csv-report")
        self.assertEqual(self.library.search("report"), [])

    def test_manifest_tampering_cannot_change_command(self):
        job, event, _ = self.observed()
        receipt = self.save(job, event)
        path = self.library.root / receipt["content_hash"] / "manifest.json"
        value = json.loads(path.read_text("utf-8"))
        value["argv"] = ["python", "-c", "print('replacement')"]
        path.chmod(0o600)
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "metadata has changed"):
            self.library.prepare("csv-report")

    def symlink(self, path, destination, *, directory=False):
        try:
            path.symlink_to(destination, target_is_directory=directory)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows symlink privilege is unavailable")
            raise

    def test_workspace_symlinks_are_rejected(self):
        job, event, _ = self.observed()
        path = self.settings.workspace / "scripts/report.py"
        outside = self.settings.data_dir / "outside.py"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        self.symlink(path, outside)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.save(job, event)

    def test_library_directory_symlink_is_rejected_on_every_access(self):
        job, event, _ = self.observed()
        self.save(job, event)
        moved = self.settings.data_dir / "moved-skills"
        self.library.root.rename(moved)
        self.symlink(self.library.root, moved, directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.library.prepare("csv-report")
        with self.assertRaisesRegex(ValueError, "symlink"):
            SkillLibrary(self.settings, self.store, self.queue)

    def test_immutable_archive_file_symlink_is_rejected(self):
        job, event, _ = self.observed()
        receipt = self.save(job, event)
        path = self.library.root / receipt["content_hash"] / "inputs/scripts/report.py"
        path.chmod(0o600)
        path.unlink()
        self.symlink(path, self.settings.workspace / "scripts/report.py")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.library.prepare("csv-report")


if __name__ == "__main__":
    unittest.main()
