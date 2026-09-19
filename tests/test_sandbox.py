import base64
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from marka import sandbox


def encoded(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class SandboxTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # Protocol/execution tests use mocks and never create a Windows process
        # group or Unix socket. Supply Linux constants solely to these mocks.
        if not hasattr(socket, "AF_UNIX"):
            self.enterContext(patch.object(socket, "AF_UNIX", 1, create=True))
        if not hasattr(signal, "SIGKILL"):
            self.enterContext(patch.object(signal, "SIGKILL", 9, create=True))

    def test_ordinary_host_cannot_execute_or_cleanup(self):
        with patch.object(sandbox.os, "getpid", return_value=42), \
                patch.object(sandbox.os, "kill") as kill, \
                patch.object(sandbox.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(RuntimeError, "PID 1"):
                sandbox.execute(["python", "-c", "print(1)"], 1, self.root)
            with self.assertRaisesRegex(RuntimeError, "PID 1"):
                sandbox._kill_other_processes()
        kill.assert_not_called()
        popen.assert_not_called()

    def test_container_guard_rejects_host_proc_mount(self):
        with patch.object(sandbox.sys, "platform", "linux"), \
                patch.object(sandbox.os, "getpid", return_value=1), \
                patch.dict(os.environ, {"MARKA_SANDBOX_CONTAINER": "1"}), \
                patch.object(Path, "is_file", return_value=True), \
                patch.object(sandbox.os, "readlink", side_effect=["pid:[host]", "pid:[private]"]):
            with self.assertRaisesRegex(RuntimeError, "namespace"):
                sandbox._require_container()

    def test_binary_inputs_and_path_policy(self):
        data = b"\x00\xff\xfe\x01binary\x00"
        self.assertEqual(sandbox._decode_files({"nested/data.bin": encoded(data)}), {"nested/data.bin": data})
        for path in ("/tmp/a", "../a", "a/../b", ".env", "a/.git/x", "a\\b", "C:/x",
                     "a:stream", "a//b", "a/", "NUL.txt", "CON", "COM¹", "a. ", "a.", "x\nname",
                     "wild*card", "question?", 'quoted"name', "a|b", "surrogate\udfff"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                sandbox._decode_files({path: ""})
        with self.assertRaisesRegex(ValueError, "collide"):
            sandbox._decode_files({"A.txt": "", "a.txt": ""})
        with self.assertRaisesRegex(ValueError, "collide"):
            sandbox._decode_files({"parent": "", "parent/child": ""})
        with self.assertRaisesRegex(ValueError, "base64"):
            sandbox._decode_files({"file": "%%%"})

    def test_file_and_total_input_limits(self):
        with self.assertRaisesRegex(ValueError, "200"):
            sandbox._decode_files({f"file-{index}": "" for index in range(201)})
        with self.assertRaisesRegex(ValueError, "512"):
            sandbox._decode_files({"large.bin": encoded(b"x" * (sandbox.MAX_FILE_BYTES + 1))})
        accepted = {f"file-{index}": encoded(b"x" * sandbox.MAX_FILE_BYTES) for index in range(4)}
        self.assertEqual(sum(len(value) for value in sandbox._decode_files(accepted).values()), 2 * 1024 * 1024)
        with self.assertRaisesRegex(ValueError, "2048"):
            sandbox._decode_files({f"file-{index}": encoded(b"x" * 400000) for index in range(6)})

    def test_only_changed_and_new_binary_outputs_are_returned(self):
        (self.root / "same.txt").write_bytes(b"same")
        (self.root / "changed.bin").write_bytes(b"\x00\xffnew")
        (self.root / "fresh.txt").write_bytes(b"fresh")
        result = sandbox._collect_files(self.root, {"same.txt": b"same", "changed.bin": b"old"})
        self.assertEqual(set(result), {"changed.bin", "fresh.txt"})
        self.assertEqual(base64.b64decode(result["changed.bin"]), b"\x00\xffnew")

    def test_unsafe_output_is_rejected_and_symlinks_are_skipped(self):
        (self.root / ".secret").write_bytes(b"not returned")
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            sandbox._collect_files(self.root, {})
        (self.root / ".secret").unlink()
        (self.root / "real.txt").write_bytes(b"real")
        try:
            (self.root / "link.txt").symlink_to(self.root / "real.txt")
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation requires privileges on this host")
        self.assertEqual(set(sandbox._collect_files(self.root, {})), {"real.txt"})

    def test_output_limits_are_explicit(self):
        (self.root / "too-large.bin").write_bytes(b"x" * (sandbox.MAX_FILE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "512"):
            sandbox._collect_files(self.root, {})
        (self.root / "too-large.bin").unlink()
        for index in range(5):
            (self.root / f"part-{index}.bin").write_bytes(b"x" * sandbox.MAX_FILE_BYTES)
        with self.assertRaisesRegex(ValueError, "2048"):
            sandbox._collect_files(self.root, {})

    def test_client_protocol_is_bounded_and_preserves_base64(self):
        transport = MagicMock()
        transport.__enter__.return_value = transport
        response = {"exit_code": 0, "_files": {"result.bin": encoded(b"\x00\xff")}}
        transport.recv.side_effect = [json.dumps(response).encode() + b"\n"]
        with patch.object(sandbox.socket, "socket", return_value=transport):
            result = sandbox.run_client("/run/test.sock", ["python", "task.py"], 3,
                                        {"task.py": encoded(b"print('ok')")})
        self.assertEqual(result, response)
        request = json.loads(transport.sendall.call_args.args[0])
        self.assertEqual(request["files"]["task.py"], encoded(b"print('ok')"))
        self.assertEqual(request["timeout"], 3)
        transport.recv.side_effect = [b"x" * (sandbox.MAX_WIRE_BYTES + 1)]
        with patch.object(sandbox.socket, "socket", return_value=transport), self.assertRaisesRegex(ValueError, "3 MiB"):
            sandbox.run_client("/run/test.sock", ["python"], 3)

    def test_client_rejects_invalid_returned_artifact_and_partial_response(self):
        transport = MagicMock()
        transport.__enter__.return_value = transport
        transport.recv.side_effect = [b'{"_files":{"../escape":""}}\n']
        with patch.object(sandbox.socket, "socket", return_value=transport), self.assertRaises(ValueError):
            sandbox.run_client("/run/test.sock", ["python"], 3)
        transport.recv.side_effect = [b'{"exit_code":0}', b""]
        with patch.object(sandbox.socket, "socket", return_value=transport), self.assertRaisesRegex(ValueError, "interrupted"):
            sandbox.run_client("/run/test.sock", ["python"], 3)

    def test_command_rejects_shell_escape_and_invalid_timeout(self):
        for argv, timeout in ((["sh", "-c", "echo x"], 1), ([], 1), (["python"], True),
                              (["python"], 0), (["python"], 61), (["python", "nul\0"], 1)):
            with self.assertRaises(ValueError):
                sandbox._validate_command(argv, timeout)

    def test_execution_uses_temporary_copy_and_cleans_before_output_collection(self):
        cleanup = MagicMock()
        process = MagicMock(pid=123, returncode=0)
        observed_work = []

        def popen(args, **kwargs):
            work = kwargs["cwd"]
            observed_work.append(work)
            self.assertTrue(work.is_relative_to(self.root))
            self.assertEqual((work / "input.bin").read_bytes(), b"\x00\xffinput")
            self.assertNotEqual(kwargs["env"]["HOME"], str(work))
            self.assertNotIn("preexec_fn", kwargs)
            self.assertEqual(args[1:3], ["-I", "-c"])
            (work / "result.bin").write_bytes(b"\xff\x00result")
            kwargs["stdout"].write(b"verified output")
            return process

        original_collect = sandbox._collect_files

        def collect(*args):
            cleanup.assert_called_once()
            return original_collect(*args)

        with patch.object(sandbox, "_require_container"), \
                patch.object(sandbox, "_kill_other_processes", cleanup), \
                patch.object(sandbox.os, "killpg", create=True), \
                patch.object(sandbox.subprocess, "Popen", side_effect=popen), \
                patch.object(sandbox, "_collect_files", side_effect=collect):
            result = sandbox.execute(["python", "-c", "ignored"], 2, self.root,
                                      {"input.bin": encoded(b"\x00\xffinput")})
        self.assertEqual(base64.b64decode(result["_files"]["result.bin"]), b"\xff\x00result")
        self.assertEqual(result["output"], "verified output")
        self.assertFalse(observed_work[0].exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_timeout_runs_namespace_cleanup(self):
        process = MagicMock(pid=123, returncode=-9)
        process.wait.side_effect = [subprocess.TimeoutExpired("synthetic", 1), None]
        with patch.object(sandbox, "_require_container"), \
                patch.object(sandbox, "_kill_other_processes") as cleanup, \
                patch.object(sandbox.os, "killpg", create=True) as killpg, \
                patch.object(sandbox.subprocess, "Popen", return_value=process):
            result = sandbox.execute(["python", "-c", "ignored"], 1, self.root)
        self.assertTrue(result["timed_out"])
        cleanup.assert_called_once()
        killpg.assert_called_once_with(123, signal.SIGKILL)

    def test_same_namespace_peer_cannot_schedule_more_execution(self):
        peer = MagicMock()
        with patch.object(socket, "SO_PEERCRED", 17, create=True):
            peer.getsockopt.return_value = struct.pack("3i", 17, 1000, 1000)
            self.assertFalse(sandbox._external_peer(peer))
            peer.getsockopt.return_value = struct.pack("3i", 0, 1000, 1000)
            self.assertTrue(sandbox._external_peer(peer))


@unittest.skipUnless(sys.platform == "linux" and os.getpid() == 1
                     and os.environ.get("MARKA_SANDBOX_CONTAINER") == "1",
                     "Live execution requires a dedicated disposable Docker PID namespace")
class LinuxSandboxIntegrationTests(unittest.TestCase):
    def test_real_binary_roundtrip_and_daemon_cleanup(self):
        with tempfile.TemporaryDirectory(dir="/workspace") as temporary:
            root = Path(temporary)
            program = ("import os,pathlib,time\n"
                       "pathlib.Path('result.bin').write_bytes(b'\\x00\\xff')\n"
                       "pid=os.fork()\n"
                       "if pid==0:\n"
                       " os.setsid()\n"
                       " time.sleep(10)\n"
                       " pathlib.Path('late.txt').write_text('escaped')\n"
                       "else:\n"
                       " print(pid,flush=True)\n")
            result = sandbox.execute(["python", "task.py"], 3, root, {"task.py": encoded(program.encode())})
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(base64.b64decode(result["_files"]["result.bin"]), b"\x00\xff")
            daemon_pid = int(result["output"].strip())
            with self.assertRaises(ProcessLookupError):
                os.kill(daemon_pid, 0)
            self.assertEqual(list(root.iterdir()), [])
