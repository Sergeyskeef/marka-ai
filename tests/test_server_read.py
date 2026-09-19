"""Read-only diagnostics fail closed and never export secrets or raw logs."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from marka import server_read

SNAPSHOT_PROTECTED = server_read._protected


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("marka_observer_test", ROOT / "deploy/observer.py")
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # CI and Windows cannot create root-owned fixtures. Test the predicate
        # separately, and exercise real fd/JSON/pagination behavior here.
        protected = patch.object(server_read, "_protected", return_value=True)
        protected.start()
        self.addCleanup(protected.stop)
        self.publish("hello")

    def publish(self, data, *, section="status", when=None):
        value = {"version": 1, "section": section, "generated_at": time.time() if when is None else when, "data": data}
        (self.root / (section + ".json")).write_text(json.dumps(value), encoding="utf-8")

    def test_only_fixed_sections_and_valid_arguments_can_be_read(self):
        for section in ("../../auth.json", "status.json", "token", "status/../config", [], {}, None):
            with self.subTest(section=section), self.assertRaises(ValueError):
                server_read.read_snapshot(self.root, section)
        for args in ({"offset": True}, {"offset": -1}, {"offset": 1048577}, {"expected_sha256": "bad"}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                server_read.read_snapshot(self.root, "status", **args)
        with self.assertRaises(OSError):
            server_read.read_snapshot(None, "status")

    def test_pagination_requires_digest_and_rejects_changed_content(self):
        text = "А" * (server_read.PAGE + 25)
        self.publish(text, section="guardian_source")
        first = server_read.read_snapshot(self.root, "guardian_source")
        self.assertEqual(first["content"], text[:server_read.PAGE])
        self.assertEqual(first["next_offset"], server_read.PAGE)
        with self.assertRaises(ValueError):
            server_read.read_snapshot(self.root, "guardian_source", offset=first["next_offset"])
        second = server_read.read_snapshot(self.root, "guardian_source", offset=first["next_offset"],
                                          expected_sha256=first["sha256"])
        self.assertEqual(first["content"] + second["content"], text)
        self.assertIsNone(second["next_offset"])
        # A new observation timestamp with identical source preserves paging.
        self.publish(text, section="guardian_source", when=time.time() + 1)
        self.assertEqual(server_read.read_snapshot(self.root, "guardian_source", offset=first["next_offset"],
                                                  expected_sha256=first["sha256"])["content"], second["content"])
        with self.assertRaises(ValueError):
            server_read.read_snapshot(self.root, "guardian_source", offset=len(text) + 1,
                                      expected_sha256=first["sha256"])
        self.publish(text + "new", section="guardian_source")
        with self.assertRaises(ValueError):
            server_read.read_snapshot(self.root, "guardian_source", offset=first["next_offset"],
                                      expected_sha256=first["sha256"])

    def test_freshness_is_exposed_and_future_metadata_is_rejected(self):
        with patch.object(server_read.time, "time", return_value=1000):
            self.publish({"healthy": True}, when=819)
            value = server_read.read_snapshot(self.root, "status")
            self.assertTrue(value["stale"])
            self.assertEqual(value["age_seconds"], 181)
            self.assertTrue(value["read_only"])
            self.publish("fresh", when=999)
            self.assertFalse(server_read.read_snapshot(self.root, "status")["stale"])
            self.publish("future", when=1061)
            with self.assertRaises(ValueError):
                server_read.read_snapshot(self.root, "status")

    def test_malformed_duplicate_nonfinite_metadata_and_oversized_json_fail(self):
        path = self.root / "status.json"
        invalid = [b"{", b"[]", b"\xff", b'{"version":1,"version":1}',
                   b'{"version":1,"section":"status","generated_at":0,"data":NaN}',
                   b'{"version":true,"section":"status","generated_at":0,"data":"bad"}',
                   b'{"version":1,"section":"config","generated_at":0,"data":"bad"}',
                   b'{"version":1,"section":"status","generated_at":true,"data":"bad"}',
                   b"x" * (server_read.MAX_BYTES + 1), b"[" * 2000 + b"]" * 2000]
        for raw in invalid:
            path.write_bytes(raw)
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                server_read.read_snapshot(self.root, "status")

    def test_directory_and_file_ownership_are_checked_independently(self):
        with patch.object(server_read, "_protected", return_value=False):
            with self.assertRaises(ValueError):
                server_read.read_snapshot(self.root, "status")
        with patch.object(server_read, "_protected", side_effect=lambda info: stat.S_ISDIR(info.st_mode)):
            with self.assertRaises(ValueError):
                server_read.read_snapshot(self.root, "status")

    def test_symlink_files_and_directories_are_never_read(self):
        link = self.root / "config.json"
        try:
            link.symlink_to(self.root / "status.json")
        except OSError:
            self.skipTest("Creating links requires platform permission")
        with self.assertRaises(ValueError):
            server_read.read_snapshot(self.root, "config")
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            server_read.read_snapshot(alias, "status")

    @unittest.skipIf(os.name == "nt", "POSIX FIFO behavior")
    def test_fifo_is_rejected_without_waiting_for_writer(self):
        os.mkfifo(self.root / "events.json", 0o600)
        started = time.monotonic()
        with self.assertRaises(ValueError):
            server_read.read_snapshot(self.root, "events")
        self.assertLess(time.monotonic() - started, 1)


class ObserverTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX snapshot ownership contract")
    def test_snapshot_requires_root_and_no_group_or_world_write(self):
        self.assertTrue(SNAPSHOT_PROTECTED(SimpleNamespace(st_uid=0, st_mode=0o100644)))
        self.assertFalse(SNAPSHOT_PROTECTED(SimpleNamespace(st_uid=10002, st_mode=0o100644)))
        self.assertFalse(SNAPSHOT_PROTECTED(SimpleNamespace(st_uid=0, st_mode=0o100664)))
        self.assertFalse(SNAPSHOT_PROTECTED(SimpleNamespace(st_uid=0, st_mode=0o40777)))

    def test_root_ownership_predicate_rejects_writable_or_nonroot_files(self):
        self.assertTrue(observer._protected(SimpleNamespace(st_uid=0, st_mode=0o100644)))
        self.assertFalse(observer._protected(SimpleNamespace(st_uid=10001, st_mode=0o100644)))
        for mode in (0o100664, 0o100646, 0o40777):
            self.assertFalse(observer._protected(SimpleNamespace(st_uid=0, st_mode=mode)))

    def test_config_exports_only_typed_allowed_values(self):
        secret = "sk-proj-CANARY_DO_NOT_PUBLISH"
        value = {"token": "123456:" + secret, "OPENAI_API_KEY": secret, "env": {"KEY": secret},
                 "voice_key_file": "/private/" + secret, "model": "gpt-5.6-sol", "reasoning_effort": "high",
                 "timezone": "UTC", "daily_calls": 200, "semantic_search": True, "max_steps": True}
        result = observer.sanitized_config(value)
        self.assertEqual(result, {"model": "gpt-5.6-sol", "reasoning_effort": "high", "timezone": "UTC",
                                  "daily_calls": 200, "semantic_search": True})
        self.assertNotIn(secret, json.dumps(result))
        invalid = observer.sanitized_config({"model": secret, "reasoning_effort": secret, "timezone": secret})
        self.assertEqual(invalid, {})

    def test_log_canaries_are_removed_but_known_module_line_and_categories_remain(self):
        raw = (b'Traceback (most recent call last):\n'
               b'  File "/private/CANARY_DIRECTORY/marka/provider.py", line 123, in complete\n'
               b'  File "/private/marka/canary_secret.py", line 999, in leak\n'
               b'TimeoutError: TOKEN_CANARY sk-proj-CANARY_API PRIVATE_CONVERSATION\n'
               b'warning: OPENAI_API_KEY=SECRET_ENV\n')
        value = observer.log_summary(raw)
        self.assertEqual(value["frames"], [{"module": "provider.py", "line": 123, "count": 1}])
        self.assertEqual(value["categories"], {"timeout": 1, "traceback": 1, "warning": 1})
        self.assertFalse(value["raw_logs_exposed"])
        text = json.dumps(value)
        for canary in ("CANARY", "PRIVATE_CONVERSATION", "SECRET_ENV", "private", "sk-proj"):
            self.assertNotIn(canary, text)

    def test_history_is_revalidated_instead_of_copying_arbitrary_previous_content(self):
        value = {"data": {"state_changes": [{"at": 1, "fingerprint": "CANARY", "secret": "CANARY",
                 "containers": [{"name": "marka-mark-1", "available": True, "running": True,
                                 "env": "CANARY"}, {"name": "unrelated-service", "available": True}],
                 "guardian": {"service_active": True, "phase": "accepted", "message": "CANARY"}}]}}
        history = observer._history(value, 2)
        self.assertEqual(len(history), 1)
        self.assertEqual(len(history[0]["containers"]), 1)
        self.assertEqual(history[0]["guardian"], {"service_active": True, "phase": "accepted"})
        self.assertNotIn("CANARY", json.dumps(history))

    def test_command_output_and_time_are_bounded_while_process_is_running(self):
        with patch.object(observer, "MAX_OUTPUT", 1024):
            with self.assertRaisesRegex(ValueError, "output limit"):
                observer.run([sys.executable, "-c", "import sys,time;sys.stdout.write('x'*4096);sys.stdout.flush();time.sleep(10)"], timeout=3)
        started = time.monotonic()
        with self.assertRaises((TimeoutError, subprocess.TimeoutExpired)):
            observer.run([sys.executable, "-c", "import time;time.sleep(10)"], timeout=0.3)
        self.assertLess(time.monotonic() - started, 3)
        result = observer.run([sys.executable, "-c", "import sys;print('out');print('err',file=sys.stderr)"], timeout=3)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), b"out")
        self.assertEqual(result.stderr.strip(), b"err")

    def test_command_environment_excludes_account_credentials_and_docker_redirects(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "CANARY", "TELEGRAM_BOT_TOKEN": "CANARY",
                                     "DOCKER_HOST": "https://private.invalid"}):
            result = observer.run([sys.executable, "-c", "import os,json;print(json.dumps(dict(os.environ)))"], timeout=3)
        env = json.loads(result.stdout)
        for name in ("OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN", "DOCKER_HOST"):
            self.assertNotIn(name, env)

    def test_collector_issues_only_fixed_read_queries_and_publishes_sanitized_snapshots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, output = Path(temporary), Path(temporary) / "published"
            (root / "masks").mkdir()
            (root / "status").mkdir()
            (root / "masks/settings.json").write_text(json.dumps({"model": "gpt-5.6-sol", "token": "CANARY"}))
            (root / "bridge.json").write_text(json.dumps({"model": "gpt-5.6-sol", "reasoning_effort": "high", "token_file": "CANARY"}))
            (root / "status/status.json").write_text(json.dumps({"phase": "accepted", "private": "CANARY"}))
            source = root / "public_source.py"
            source.write_text("# public source\n")
            queries = []

            def run(argv):
                queries.append(argv)
                if "inspect" in argv:
                    data = json.dumps({"running": True, "image": "sha256:" + "a" * 64, "Env": ["CANARY"]}).encode()
                elif "logs" in argv:
                    data = b'TimeoutError: CANARY\n  File "/private/marka/app.py", line 10, in run\n'
                else:
                    data = b"active\n"
                return subprocess.CompletedProcess(argv, 0, data, b"")

            with patch.object(observer, "run", side_effect=run), \
                    patch.object(observer.os, "geteuid", return_value=0, create=True), \
                    patch.object(observer, "_protected", return_value=True), \
                    patch.object(observer, "SOURCES", (("guardian_source", source), ("observer_source", source))), \
                    patch.object(server_read, "_protected", return_value=True):
                self.assertTrue(observer.collect(root, output)["ok"])
                self.assertEqual(len(queries), 7)
                for argv in queries[:-1]:
                    self.assertEqual(argv[:2], list(observer.DOCKER_PREFIX))
                    self.assertIn(argv[-1], observer.CONTAINERS)
                    self.assertIn(argv[2], {"inspect", "logs"})
                    if argv[2] == "inspect":
                        self.assertIn("--format=" + observer.INSPECT_FORMAT, argv)
                        self.assertNotIn("Env", observer.INSPECT_FORMAT)
                self.assertEqual(queries[-1], ["/usr/bin/systemctl", "is-active", "marka-guardian.service"])
                for section in server_read.SECTIONS:
                    text = server_read.read_snapshot(output, section)["content"]
                    self.assertNotIn("CANARY", text)
                    self.assertNotIn("/private", text)
                first = json.loads((output / "events.json").read_text())["data"]["state_changes"]
                self.assertEqual(len(first), 1)
                # Existing unfinished publications must not wedge the next pass.
                (output / ".status.pending").write_text("orphan")
                observer.collect(root, output)
                self.assertEqual(len(json.loads((output / "events.json").read_text())["data"]["state_changes"]), 1)


if __name__ == "__main__":
    unittest.main()
