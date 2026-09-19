"""Fault tests for the independent host controller; no Docker or credentials."""
import copy
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("independent_guardian", Path(__file__).resolve().parents[1] / "deploy" / "guardian.py")
guardian = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guardian)

BASE = "sha256:" + "1" * 64
NEW = "sha256:" + "2" * 64
OTHER = "sha256:" + "3" * 64


@contextmanager
def connection(path):
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


def make_database(path, owner=42):
    with connection(path) as db:
        db.executescript("""
          CREATE TABLE events(id INTEGER PRIMARY KEY,role TEXT,content TEXT,session TEXT,created_at TEXT,meta TEXT);
          CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
          CREATE TABLE jobs(id TEXT PRIMARY KEY,prompt TEXT,chat_id INTEGER,source TEXT,state TEXT,due REAL,inflight INTEGER,deadline REAL,error TEXT,updated REAL);
          CREATE TABLE deliveries(id INTEGER PRIMARY KEY,source TEXT,chat_id INTEGER,text TEXT,state TEXT,error TEXT);
        """)
        db.execute("INSERT INTO meta VALUES('owner_id',?)", (str(owner),))
        db.execute("INSERT INTO events VALUES(1,'user','original owner evidence','main','2026-09-19','{}')")


class FakeDocker:
    def __init__(self):
        self.row = {"image": BASE, "running": True, "oom": False, "restarts": 0, "exit": 0}
        self.launched = []
        self.removed = []
        self.fail_validation = False
        self.fail_launch = False
        self.stage = None

    def inspect(self):
        return dict(self.row) if self.row else None

    def stop(self):
        if self.row:
            self.row["running"] = False

    def launch(self, image):
        self.launched.append(image)
        if self.fail_launch:
            raise guardian.Rejected("Docker operation failed")
        self.row = {"image": image, "running": True, "oom": False, "restarts": 0, "exit": 0}

    def build(self, stage, image):
        self.stage = Path(stage)
        if image != BASE:
            raise AssertionError("build must use fixed original base")
        return NEW

    def validate(self, image, stage):
        if self.fail_validation:
            raise guardian.Rejected("independent regression checks failed")
        return {"tests": 400, "fixture": {"verified": True}}

    def remove_image(self, image):
        self.removed.append(image)


class GuardianTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "private"
        self.root.mkdir(mode=0o700)
        self.state_dir = self.base / "state"
        self.state_dir.mkdir()
        self.inbox = self.base / "inbox"
        self.inbox.mkdir()
        self.source = self.base / "trusted"
        (self.source / "src/marka").mkdir(parents=True)
        (self.source / "src/marka/example.py").write_text("VALUE = 1\n", encoding="utf-8")
        self.db = self.state_dir / "marka.sqlite3"
        make_database(self.db)
        self.journal = self.base / "journal.sqlite3"
        with connection(self.journal) as db:
            db.execute("CREATE TABLE updates(update_id INTEGER PRIMARY KEY,owner_id INTEGER,control TEXT,raw TEXT)")
            db.execute("INSERT INTO updates VALUES(10,42,'','{}')")
        self.config = {"version": 1, "current_image": BASE, "fallback_image": BASE,
                       "trusted_source_dir": str(self.source), "root_dir": str(self.root),
                       "state_path": str(self.state_dir), "inbox": str(self.inbox),
                       "bridge_journal": str(self.journal), "owner_id": 42,
                       "status_path": str(self.base / "status/status.json"),
                       "recovery_reserve_bytes": 0,
                       "startup_grace": 5, "heartbeat_timeout": 10, "probation_seconds": 15,
                       "container": {"name": "marka-mark-1", "mounts": [{"type": "volume", "source": "marka_state", "target": "/state"}]}}
        self.now = 1000.0
        self.docker = FakeDocker()
        # A CI worker is not host root. Only the stat ownership observation is
        # adapted; production entrypoint always requires actual root and flock.
        if os.name != "nt" and os.getuid() != 0:
            patch = mock.patch.object(guardian, "root_protected", return_value=True)
            patch.start()
            self.addCleanup(patch.stop)
            chown = mock.patch.object(guardian.os, "chown")
            chown.start()
            self.addCleanup(chown.stop)
        self.controller = guardian.Guardian(self.config, self.docker, now=lambda: self.now, free=lambda _: 8 * 1024**3)
        self.controller.initialize_checkpoint()
        self.heartbeat()

    def heartbeat(self):
        guardian.atomic(self.state_dir / "heartbeat.json", guardian.canonical({"version": 1, "phase": "running", "started": self.now,
                         "tick": self.now, "worker_progress": self.now, "job_id": "", "boot_id": "fixture"}))

    def proposal(self, identifier="first", text="VALUE = 2\n"):
        baseline = {"src/marka/example.py": "VALUE = 1\n"}
        candidate = {"src/marka/example.py": text}
        return {"version": 1, "request_id": identifier, "experiment_id": "experiment", "job_id": "job",
                "source": "telegram:10", "objective": "Improve fixture", "baseline": baseline, "candidate": candidate,
                "baseline_manifest": guardian.manifest(baseline), "candidate_manifest": guardian.manifest(candidate)}

    def submit(self, request=None):
        request = request or self.proposal()
        path = self.inbox / (request["request_id"] + ".json")
        path.write_bytes(guardian.canonical(request))
        self.controller.tick()
        return path

    def probation(self):
        self.submit()
        for _ in range(4):
            self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "probation")
        self.heartbeat()

    def restart(self):
        self.controller = guardian.Guardian(self.config, self.docker, now=lambda: self.now, free=lambda _: 8 * 1024**3)

    def test_happy_path_captures_exact_bytes_and_accepts_after_probation(self):
        self.probation()
        self.assertEqual(self.docker.row["image"], NEW)
        self.now += 16
        self.heartbeat()
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "accepted")
        self.assertEqual(self.controller.state["current_image"], NEW)
        self.assertEqual(guardian.db_fingerprint(self.db)["count"], 1)
        public = json.loads(Path(self.config["status_path"]).read_text())
        self.assertNotIn("current_sources", public)
        self.assertNotIn("checkpoint", public)
        if os.name != "nt":
            self.assertEqual((self.docker.stage / "src/marka/example.py").stat().st_mode & 0o777, 0o644)

    def test_stale_baseline_rejected_without_stop(self):
        request = self.proposal()
        request["baseline"]["src/marka/example.py"] = "VALUE = 0\n"
        request["baseline_manifest"] = guardian.manifest(request["baseline"])
        self.submit(request)
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "rejected")
        self.assertTrue(self.docker.row["running"])
        self.assertEqual(self.docker.launched, [])

    def test_capture_is_immutable_after_bot_rewrites_request(self):
        path = self.submit()
        path.write_text("malicious replacement", encoding="utf-8")
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "waiting_idle")
        self.assertEqual((self.docker.stage / "src/marka/example.py").read_text(), "VALUE = 2\n")

    def test_durable_capture_consumes_outgoing_inbox(self):
        path = self.submit()
        self.assertFalse(path.exists())
        protected = Path(self.controller.state["active"]["stage"]) / "request.json"
        self.assertTrue(protected.is_file())
        self.assertEqual(guardian.json_object(protected.read_bytes())["request_id"], "first")

    def test_emergency_reserve_released_only_for_low_space_recovery(self):
        reserve = self.root / "recovery-reserve.bin"
        guardian.atomic(reserve, b"reserved synthetic bytes")
        self.assertFalse(self.controller.release_recovery_reserve(1024))
        self.assertTrue(reserve.exists())
        self.controller.free = lambda _: 0
        self.assertTrue(self.controller.release_recovery_reserve(1024))
        self.assertFalse(reserve.exists())

    def test_reserve_allocator_uses_preallocation_without_large_test_file(self):
        self.controller.cfg['recovery_reserve_bytes'] = 128 * 1024**2
        def fake_allocate(fd, offset, size):
            self.assertEqual(offset, 0)
            self.assertEqual(size, 128 * 1024**2)
            os.write(fd, b"synthetic allocation")
        with mock.patch.object(guardian.os, 'posix_fallocate', side_effect=fake_allocate, create=True) as allocate:
            self.controller.ensure_recovery_reserve()
        allocate.assert_called_once()
        self.assertEqual((self.root / 'recovery-reserve.bin').read_bytes(), b"synthetic allocation")

    def test_recovery_frees_reserve_before_persisting_transition(self):
        reserve = self.root / 'recovery-reserve.bin'
        guardian.atomic(reserve, b"reserved blocks")
        self.controller.free = lambda _: 0
        self.controller.begin_recovery('synthetic disk full')
        self.assertFalse(reserve.exists())
        self.assertEqual(self.controller.state['phase'], 'rolling_back')

    def test_consumed_reserve_does_not_block_watchdog_restart(self):
        self.controller.cfg['recovery_reserve_bytes'] = 128 * 1024**2
        self.controller.free = lambda _: 0
        self.controller.initialize_checkpoint()
        self.assertTrue(Path(self.controller.state['checkpoint']).exists())

    def test_duplicate_rejected_candidate_not_retested(self):
        self.docker.fail_validation = True
        self.submit()
        self.controller.tick()
        self.docker.fail_validation = False
        self.submit(self.proposal("second"))
        self.controller.tick()
        self.assertEqual(self.controller.state["reason"], "candidate was already rejected")

    def test_duplicate_request_is_not_activated_twice(self):
        self.probation()
        self.now += 16
        self.heartbeat()
        self.controller.tick()
        self.controller.tick()
        self.assertEqual(self.docker.launched, [NEW])

    def test_symlink_request_refused(self):
        target = self.base / "private-request.json"
        target.write_bytes(guardian.canonical(self.proposal()))
        try:
            (self.inbox / "first.json").symlink_to(target)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.controller.tick()
        self.assertEqual(self.controller.state["seen"]["first"], "rejected")

    def test_disk_reserve_refuses_before_capture(self):
        self.controller.free = lambda _: guardian.RESERVE - 1
        self.submit()
        self.assertEqual(self.controller.state["seen"]["first"], "rejected")
        self.assertIsNone(self.controller.state["active"])
        self.assertTrue(self.docker.row["running"])

    def test_waits_for_active_work_but_allows_future_schedule(self):
        with connection(self.db) as db:
            db.execute("INSERT INTO jobs VALUES('job','work',42,'telegram:10','running',0,0,2000,'',0)")
        self.submit()
        self.controller.tick()
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "waiting_idle")
        with connection(self.db) as db:
            db.execute("UPDATE jobs SET state='queued',due=3000")
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "checkpoint")

    def test_import_crash_rolls_back_without_losing_events(self):
        self.probation()
        self.docker.row.update(running=False, exit=1)
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "rolling_back")
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "recovered")
        self.assertEqual(self.docker.row["image"], BASE)
        self.assertEqual(guardian.db_fingerprint(self.db)["count"], 1)

    def test_stale_loop_heartbeat_rolls_back(self):
        self.probation()
        self.now += 16
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "rolling_back")
        self.assertIn("heartbeat", self.controller.state["reason"])

    def test_external_api_error_alone_is_not_a_rollback_signal(self):
        self.probation()
        with connection(self.db) as db:
            db.execute("INSERT INTO jobs VALUES('job','work',42,'telegram:10','blocked',0,0,0,'provider temporarily unavailable',0)")
        self.now += 16
        self.heartbeat()
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "accepted")

    def test_guardian_restart_during_activation_recovers(self):
        self.submit()
        for _ in range(3):
            self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "activating")
        self.docker.launch(NEW)  # power cut before the probation state persisted
        self.restart()
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "rolling_back")
        self.controller.tick()
        self.assertEqual(self.docker.row["image"], BASE)

    def test_guardian_restart_before_activation_finishes_switch(self):
        self.submit()
        for _ in range(3):
            self.controller.tick()
        self.restart()
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "probation")

    def test_corrupt_db_quarantined_restored_and_unfinished_jobs_blocked(self):
        with connection(self.db) as db:
            db.execute("INSERT INTO jobs VALUES('future','work',42,'future','queued',3000,0,0,'',0)")
            db.execute("INSERT INTO deliveries VALUES(1,'pending',42,'reply','pending','')")
        self.probation()
        self.db.write_bytes(b"broken canonical database")
        with connection(self.journal) as db:
            db.execute("INSERT INTO updates VALUES(11,42,'','{\"new_input\":true}')")
        self.controller.tick()
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "recovered")
        self.assertTrue(self.controller.state["last_result"]["restored_database"])
        with connection(self.db) as db:
            self.assertEqual(db.execute("SELECT state FROM jobs WHERE id='future'").fetchone()[0], "blocked")
            self.assertEqual(db.execute("SELECT state FROM deliveries").fetchone()[0], "uncertain")
        with connection(self.journal) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM updates").fetchone()[0], 2)
        self.assertEqual(len(list(self.root.glob("quarantine-*"))), 1)

    def test_healthy_db_rollback_preserves_new_events_and_future_jobs(self):
        self.probation()
        with connection(self.db) as db:
            db.execute("INSERT INTO events VALUES(2,'user','new input','main','2026-09-19','{}')")
            db.execute("INSERT INTO jobs VALUES('future','work',42,'future','queued',3000,0,0,'',0)")
            db.execute("INSERT INTO jobs VALUES('busy','work',42,'busy','running',0,1,3000,'',0)")
            db.execute("INSERT INTO deliveries VALUES(1,'sending',42,'reply','sending','')")
        self.docker.row["running"] = False
        self.controller.tick()
        self.controller.tick()
        with connection(self.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT state FROM jobs WHERE id='future'").fetchone()[0], "queued")
            self.assertEqual(db.execute("SELECT state FROM jobs WHERE id='busy'").fetchone()[0], "blocked")
            self.assertEqual(db.execute("SELECT state FROM deliveries").fetchone()[0], "uncertain")

    def test_owner_rescue_works_when_bot_cannot_answer(self):
        self.docker.row["running"] = False
        with connection(self.journal) as db:
            db.execute("INSERT INTO updates VALUES(11,42,'rescue','{}')")
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "recovered")
        self.assertEqual(self.controller.state["last_control"], 11)
        self.controller.tick()
        self.assertEqual(len(self.docker.launched), 1)

    def test_rescue_forces_restore_even_when_database_integrity_passes(self):
        with connection(self.db) as db:
            db.execute("INSERT INTO meta VALUES('unsafe_setting','changed')")
        with connection(self.journal) as db:
            db.execute("INSERT INTO updates VALUES(11,42,'rescue','{}')")
        self.controller.tick()
        self.assertTrue(self.controller.state["last_result"]["restored_database"])
        with connection(self.db) as db:
            self.assertIsNone(db.execute("SELECT value FROM meta WHERE key='unsafe_setting'").fetchone())

    def test_rollback_preserves_healthy_database(self):
        with connection(self.db) as db:
            db.execute("INSERT INTO meta VALUES('new_setting','preserve')")
        with connection(self.journal) as db:
            db.execute("INSERT INTO updates VALUES(11,42,'rollback','{}')")
        self.controller.tick()
        self.assertFalse(self.controller.state["last_result"]["restored_database"])
        with connection(self.db) as db:
            self.assertEqual(db.execute("SELECT value FROM meta WHERE key='new_setting'").fetchone()[0], "preserve")

    def test_unknown_owner_source_refused(self):
        request = self.proposal()
        request["source"] = "telegram:999"
        self.submit(request)
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "rejected")

    def test_image_changed_by_operator_is_not_overwritten(self):
        self.submit()
        self.controller.tick()
        self.docker.row["image"] = OTHER
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "rejected")
        self.assertEqual(self.docker.launched, [])

    def test_history_tampering_restores_checkpoint(self):
        self.probation()
        with connection(self.db) as db:
            db.execute("UPDATE events SET content='changed' WHERE id=1")
        self.controller.tick()
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "recovered")
        with connection(self.db) as db:
            self.assertEqual(db.execute("SELECT content FROM events WHERE id=1").fetchone()[0], "original owner evidence")

    def test_schema_damage_restores_even_with_valid_history_and_integrity(self):
        self.probation()
        with connection(self.db) as db:
            db.execute("DROP TABLE deliveries")
        self.assertEqual(guardian.db_fingerprint(self.db)["count"], 1)
        self.controller.tick()
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "recovered")
        self.assertTrue(self.controller.state["last_result"]["restored_database"])
        with connection(self.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM deliveries").fetchone()[0], 0)

    def test_new_required_column_breaking_old_inserts_is_incompatible(self):
        expected = guardian.db_schema(self.db)
        with connection(self.db) as db:
            db.execute("ALTER TABLE deliveries ADD COLUMN required TEXT NOT NULL")
        self.assertFalse(guardian.schema_compatible(self.db, expected))

    def test_new_unique_index_on_existing_table_breaks_compatibility(self):
        expected = guardian.db_schema(self.db)
        with connection(self.db) as db:
            db.execute("CREATE UNIQUE INDEX new_constraint ON events(session,created_at)")
        self.assertFalse(guardian.schema_compatible(self.db, expected))

    def test_nullable_column_breaking_positional_insert_restores_checkpoint(self):
        self.probation()
        with connection(self.db) as db:
            db.execute("ALTER TABLE deliveries ADD COLUMN extra TEXT")
        self.docker.row["running"] = False
        self.controller.tick()
        self.controller.tick()
        self.assertTrue(self.controller.state["last_result"]["restored_database"])
        self.assertEqual(len(guardian.db_schema(self.db)["tables"]["deliveries"]), 6)

    def test_crashed_current_bot_during_idle_wait_recovers_immediately(self):
        with connection(self.db) as db:
            db.execute("INSERT INTO jobs VALUES('busy','work',42,'busy','running',0,1,3000,'',0)")
        self.submit()
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "waiting_idle")
        self.docker.row["running"] = False
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "rolling_back")
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "recovered")

    def test_candidate_trigger_cannot_prevent_checkpoint_recovery(self):
        self.probation()
        with connection(self.db) as db:
            db.execute("INSERT INTO jobs VALUES('busy','work',42,'busy','running',0,1,3000,'',0)")
            db.execute("CREATE TRIGGER break_recovery BEFORE UPDATE ON jobs BEGIN SELECT RAISE(ABORT,'broken trigger'); END")
        self.docker.row["running"] = False
        self.controller.tick()
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "recovered")
        self.assertTrue(self.controller.state["last_result"]["restored_database"])

    def test_malformed_heartbeat_cannot_crash_guardian(self):
        self.probation()
        self.now += 10
        guardian.atomic(self.state_dir / "heartbeat.json", guardian.canonical({"version": 1, "phase": "running", "tick": self.now, "started": []}))
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "rolling_back")

    def test_oversized_event_is_rejected_before_python_row_materialization(self):
        with connection(self.db) as db:
            db.execute("UPDATE events SET content=?", ("a" * (guardian.MAX_EVENT_BYTES + 1),))
        with self.assertRaisesRegex(guardian.Rejected, "inspection bound"):
            guardian.db_fingerprint(self.db)

    def test_out_of_range_owner_id_rejected_without_sql_overflow(self):
        request = self.proposal()
        request["source"] = "telegram:99999999999999999999"
        self.submit(request)
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "rejected")

    def test_checkpoint_initialization_is_idempotent(self):
        original = guardian.read_regular(self.root / "bootstrap.sqlite3", 1024 * 1024)
        self.controller.initialize_checkpoint()
        self.assertEqual(guardian.read_regular(self.root / "bootstrap.sqlite3", 1024 * 1024), original)

    def test_bounded_recovery_stops_restarting_bad_fallback(self):
        for _ in range(2):
            self.docker.row["running"] = False
            self.now += 20
            self.controller.tick()
            self.controller.tick()
            self.assertEqual(self.controller.state["phase"], "recovered")
        self.docker.row["running"] = False
        self.now += 20
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "manual_intervention")
        self.assertEqual(self.docker.launched, [BASE, BASE])

    def test_output_capture_is_bounded_before_allocation(self):
        adapter = guardian.Docker(self.config)
        real_popen = subprocess.Popen
        def output_process(*args, **kwargs):
            return real_popen([sys.executable, "-c", "import sys,time; sys.stdout.write('x'*5000000); sys.stdout.flush(); time.sleep(2)"], **kwargs)
        with mock.patch.object(guardian.subprocess, "Popen", side_effect=output_process):
            with self.assertRaisesRegex(guardian.Rejected, "output exceeded"):
                adapter.command(["inspect", "fixture"], timeout=5)

    def test_build_uses_verified_local_tag_and_pinned_layer_prefix(self):
        stage = self.root / 'build-fixture'
        stage.mkdir()
        adapter = guardian.Docker(self.config)
        calls = []
        def command(arguments, **kwargs):
            calls.append(arguments)
            value = b''
            if arguments[:2] == ['image', 'inspect']:
                candidate = arguments[2].startswith('marka-guardian-candidate:')
                value = json.dumps([{'Id': NEW if candidate else BASE,
                                     'RootFS': {'Type': 'layers', 'Layers': ['layer-one', 'layer-two'] + (['candidate-layer'] if candidate else [])}}]).encode()
            return subprocess.CompletedProcess(arguments, 0, value, b'')
        adapter.command = command
        self.assertEqual(adapter.build(stage, BASE), NEW)
        content = (stage / 'Dockerfile').read_text()
        self.assertTrue(content.startswith('FROM marka-guardian-base:'))
        self.assertNotIn('FROM sha256:', content)
        self.assertEqual(calls[1][:2], ['tag', BASE])
        self.assertIn('--network=none', next(row for row in calls if row[0] == 'build'))
        self.assertIn('--pull=false', next(row for row in calls if row[0] == 'build'))
        self.assertEqual(calls[-1][:2], ['image', 'rm'])

    def test_build_refuses_retagged_base_and_foreign_result_layers(self):
        for failure in ('tag', 'layers'):
            stage = self.root / ('build-' + failure)
            stage.mkdir()
            adapter = guardian.Docker(self.config)
            calls = []
            def command(arguments, **kwargs):
                calls.append(arguments)
                value = b''
                if arguments[:2] == ['image', 'inspect']:
                    name = arguments[2]
                    identifier = BASE
                    layers = ['base-layer']
                    if name.startswith('marka-guardian-base:') and failure == 'tag':
                        identifier = OTHER
                    if name.startswith('marka-guardian-candidate:'):
                        identifier, layers = NEW, ['foreign-base-layer']
                    value = json.dumps([{'Id': identifier, 'RootFS': {'Type': 'layers', 'Layers': layers}}]).encode()
                return subprocess.CompletedProcess(arguments, 0, value, b'')
            adapter.command = command
            with self.assertRaises(guardian.Rejected):
                adapter.build(stage, BASE)
            self.assertEqual(calls[-1][:2], ['image', 'rm'])

    def test_request_scope_and_manifest_validation(self):
        baseline = self.proposal()["baseline"]
        for mutate in (lambda r: r.update(command="anything"),
                       lambda r: r.update(candidate_manifest="0" * 64),
                       lambda r: r["candidate"].update({"src/marka/example.py": "x="}),
                       lambda r: r.update(objective="")):
            request = self.proposal()
            mutate(request)
            with self.assertRaises(guardian.Rejected):
                guardian.validate_request(request, baseline, lambda _: True)

    def test_candidate_report_hash_checked(self):
        request = self.proposal()
        request["report"] = {"status": "pass"}
        request["report_sha256"] = guardian.digest(guardian.canonical(request["report"]))
        guardian.validate_request(request, request["baseline"], lambda _: True)
        request["report"]["status"] = "failed"
        with self.assertRaises(guardian.Rejected):
            guardian.validate_request(request, request["baseline"], lambda _: True)

    def test_duplicate_json_keys_refused(self):
        with self.assertRaises(guardian.Rejected):
            guardian.json_object(b'{"version":1,"version":2}')

    def test_database_symlink_is_not_followed(self):
        other = self.base / "other.sqlite3"
        self.db.replace(other)
        try:
            self.db.symlink_to(other)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaises(guardian.Rejected):
            guardian.db_fingerprint(self.db)

    def test_stable_watchdog_can_restore_bootstrap_checkpoint(self):
        self.db.write_bytes(b"corrupt before any upgrade")
        self.now += 6
        self.controller.tick()
        self.controller.tick()
        self.assertEqual(self.controller.state["phase"], "recovered")
        self.assertEqual(guardian.db_fingerprint(self.db)["count"], 1)

    def test_fixed_fixture_runs_against_real_runtime(self):
        location = str(self.base / "fixture.sqlite3").replace("\\", "/")
        code = guardian.FIXTURE.replace("/state/fixture.sqlite3", location)
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=20, env=env)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(guardian.db_fingerprint(Path(location))["owner"], "424242")


if __name__ == "__main__":
    unittest.main()
