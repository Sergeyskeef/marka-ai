"""Installed-source navigation uses exact bounded pages and literal search."""

from __future__ import annotations

import hashlib
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from marka.config import Settings
from marka.evolution import Evolution
from marka.tools import Tools, Workspace


class SourceNavigationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "release" / "src" / "marka"
        self.tests = self.root / "release" / "tests"
        self.source.mkdir(parents=True)
        self.tests.mkdir()
        (self.source / "sample.py").write_bytes(b"def example():\n    return 1\n")
        (self.source / "identity.md").write_text("Installed public identity", "utf-8")
        (self.tests / "test_sample.py").write_text("# shipped regression\n", "utf-8")
        self.settings = Settings(self.root / "state")
        self.settings.prepare()
        self.evolution = Evolution(self.settings, Workspace(self.settings.workspace),
                                   source_root=self.source, test_root=self.tests)

    def write_source(self, text, name="sample.py"):
        (self.source / name).write_bytes(text.encode("utf-8"))
        return "src/marka/" + name

    def test_pages_reconstruct_long_unicode_crlf_source_with_exact_line_metadata(self):
        text = "# заголовок\r\n" + "Ж" * 26001 + "\r\n" + "# tail value\r\n" * 3000
        path = self.write_source(text)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        first = self.evolution.inspect(path)
        self.assertEqual(first["end_line"], 2, "A partial long line must not claim all requested lines")
        self.assertEqual(first["start_line"], 1)
        self.assertEqual(first["next_offset"], 12000)
        self.assertEqual(first["total_lines"], 3002)
        self.assertGreater(first["total_chars"], 60000)
        pages, result = [], first
        while True:
            self.assertLessEqual(len(result["content"]), 12000)
            self.assertEqual(result["sha256"], digest)
            self.assertEqual(result["total_chars"], len(text))
            self.assertEqual(result["content"], text[result["offset"]:result["offset"] + len(result["content"])])
            pages.append(result["content"])
            if result["next_offset"] is None:
                break
            result = self.evolution.inspect(path, offset=result["next_offset"], expected_sha256=digest)
        self.assertEqual("".join(pages), text)
        self.assertEqual(result["end_line"], 3002)

    def test_line_selection_and_offset_continuation_have_no_gap(self):
        text = "first\nsecond\nthird\nfourth\n"
        path = self.write_source(text)
        page = self.evolution.inspect(path, start_line=2, end_line=2)
        self.assertEqual(page["content"], "second\n")
        self.assertEqual((page["start_line"], page["end_line"]), (2, 2))
        self.assertEqual(page["offset"], len("first\n"))
        next_page = self.evolution.inspect(path, offset=page["next_offset"], expected_sha256=page["sha256"])
        self.assertEqual(page["content"] + next_page["content"], text[len("first\n"):])
        self.assertEqual((next_page["start_line"], next_page["end_line"]), (3, 4))
        self.assertIsNone(next_page["next_offset"])

    def test_tool_dispatch_keeps_absolute_pages_and_search_locations(self):
        text = "# header\n" * 170 + "# needle " + "Ж" * 25000 + "\n# end\n"
        path = self.write_source(text)
        tools = Tools(self.settings, None, None)

        async def exercise():
            first = await tools.call("self.inspect", {"path": path, "start_line": 171, "end_line": 172}, {}, [], 1)
            second = await tools.call("self.inspect", {"path": path, "offset": first["next_offset"],
                                                       "expected_sha256": first["sha256"]}, {}, [], 2)
            third = await tools.call("self.inspect", {"path": path, "offset": second["next_offset"],
                                                      "expected_sha256": second["sha256"]}, {}, [], 3)
            found = await tools.call("self.search", {"query": "needle", "path": path, "limit": 1}, {}, [], 4)
            return first, second, third, found

        with patch("marka.evolution.Evolution", return_value=self.evolution):
            first, second, third, found = asyncio.run(exercise())
        begin = len("# header\n" * 170)
        self.assertEqual(first["offset"], begin)
        self.assertEqual((first["start_line"], first["end_line"]), (171, 171))
        self.assertEqual(first["content"] + second["content"] + third["content"], text[begin:])
        self.assertIsNone(third["next_offset"])
        self.assertEqual(found["matches"][0]["line"], 171)
        self.assertEqual(found["matches"][0]["sha256"], first["sha256"])

    def test_empty_and_past_end_pages_do_not_invent_line_ranges(self):
        empty = self.evolution.inspect(self.write_source(""))
        self.assertEqual(empty["content"], "")
        self.assertEqual(empty["total_lines"], 0)
        self.assertIsNone(empty["start_line"])
        self.assertIsNone(empty["end_line"])
        path = self.write_source("one\n")
        for args in ({"start_line": 50, "end_line": 60}, {"offset": 999999}):
            result = self.evolution.inspect(path, **args)
            self.assertEqual(result["offset"], 4)
            self.assertEqual(result["content"], "")
            self.assertIsNone(result["next_offset"])
            self.assertIsNone(result["start_line"])
            self.assertIsNone(result["end_line"])

    def test_changed_source_rejects_expected_hash(self):
        path = self.write_source("# before\n")
        before = self.evolution.inspect(path)
        self.write_source("# after\n")
        with self.assertRaisesRegex(ValueError, "source changed"):
            self.evolution.inspect(path, offset=2, expected_sha256=before["sha256"])

    def test_current_file_size_limit_is_visible_without_claiming_smaller_proposal_is_impossible(self):
        path = self.write_source("#" + "Ж" * 32000)
        page = self.evolution.inspect(path)
        self.assertEqual(page["self_change_proposal_limit_bytes"], 60000)
        self.assertFalse(page["self_change_size_eligible"])
        self.assertEqual(page["self_change_size_reason"], "current_file_exceeds_proposal_limit")
        self.assertIn("smaller proposed module may fit", page["self_change_size_note"])
        index = self.evolution.inspect()
        self.assertEqual(index["self_change_proposal_limit_bytes"], 60000)
        indexed = next(item for item in index["files"] if item["path"] == path)
        self.assertFalse(indexed["self_change_size_eligible"])
        self.assertEqual(Evolution._changes({path: "pass\n"})[path], b"pass\n")
        self.write_source("pass\n")
        smaller = self.evolution.inspect(path)
        self.assertTrue(smaller["self_change_size_eligible"])
        self.assertIsNone(smaller["self_change_size_reason"])

    def test_literal_search_returns_true_offsets_and_excerpt_for_long_line(self):
        literal = "a.*[b]"
        text = "# ab does not match regex syntax\r\n" + "Ж" * 20000 + literal + " suffix\r\n" + literal.upper() + "\n"
        path = self.write_source(text)
        with patch("subprocess.Popen", side_effect=AssertionError("Search must not execute a command")):
            result = self.evolution.search(literal, path=path)
        self.assertEqual(len(result["matches"]), 1)
        match = result["matches"][0]
        self.assertEqual(match["line"], 2)
        self.assertEqual(match["column"], 20001)
        self.assertEqual(text[match["offset"]:match["end_offset"]], literal)
        self.assertIn(literal, match["excerpt"])
        self.assertLessEqual(len(match["excerpt"]), 240)
        self.assertEqual(match["excerpt"], text[match["excerpt_offset"]:match["excerpt_offset"] + len(match["excerpt"])])
        page = self.evolution.inspect(match["path"], offset=match["excerpt_offset"], expected_sha256=match["sha256"])
        self.assertIn(literal, page["content"])
        self.assertTrue(result["case_sensitive"])
        self.assertTrue(result["literal"])

    def test_search_limit_reports_only_observed_truncation(self):
        path = self.write_source("needle\nneedle\nneedle\n")
        limited = self.evolution.search("needle", path, limit=2)
        self.assertEqual(len(limited["matches"]), 2)
        self.assertTrue(limited["truncated"])
        exact = self.evolution.search("needle", path, limit=3)
        self.assertEqual(len(exact["matches"]), 3)
        self.assertFalse(exact["truncated"])
        self.assertEqual(self.evolution.search("absent", path)["matches"], [])

    def test_index_and_search_exclude_private_hidden_and_non_file_entries(self):
        canary = "SYNTHETIC_PRIVATE_SOURCE_CANARY"
        (self.source / ".private.py").write_text(canary, "utf-8")
        (self.source / "credentials.json").write_text(canary, "utf-8")
        (self.tests / ".hidden.py").write_text(canary, "utf-8")
        (self.tests / "directory.py").mkdir()
        (self.settings.workspace / "private.py").write_text(canary, "utf-8")
        deploy = self.tests.parent / "deploy"
        deploy.mkdir()
        (deploy / "guardian.py").write_text("# installed guardian\n", "utf-8")
        (deploy / "private.env").write_text(canary, "utf-8")
        index = self.evolution.inspect()
        names = {item["path"] for item in index["files"]}
        self.assertIn("deploy/guardian.py", names)
        self.assertIn("src/marka/identity.md", names)
        self.assertIn("tests/test_sample.py", names)
        self.assertFalse(index["canonical_tests_editable"])
        self.assertEqual(index["promotion"], "none")
        self.assertNotIn(canary, json.dumps(index))
        self.assertEqual(self.evolution.search(canary)["matches"], [])
        for path in ("src/marka/.private.py", "tests/.hidden.py", "credentials.json", "private.py", "deploy/private.env"):
            with self.assertRaises(ValueError):
                self.evolution.inspect(path)

    def test_symlink_files_and_directories_cannot_extend_public_scope(self):
        secret = self.root / "private_source.py"
        secret.write_text("SYMLINK_CANARY", "utf-8")
        private = self.root / "private_tests"
        private.mkdir()
        (private / "test_private.py").write_text("SYMLINK_CANARY", "utf-8")
        (private / "guardian.py").write_text("SYMLINK_CANARY", "utf-8")
        try:
            (self.source / "linked.py").symlink_to(secret)
            (self.tests / "linked").symlink_to(private, target_is_directory=True)
            (self.tests.parent / "deploy").symlink_to(private, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation is unavailable")
        self.assertEqual(self.evolution.search("SYMLINK_CANARY")["matches"], [])
        names = {item["path"] for item in self.evolution.inspect()["files"]}
        self.assertNotIn("src/marka/linked.py", names)
        self.assertNotIn("tests/linked/test_private.py", names)
        self.assertNotIn("deploy/guardian.py", names)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO check")
    def test_fifo_test_source_is_not_opened(self):
        os.mkfifo(self.tests / "test_pipe.py")
        self.assertEqual(self.evolution.search("absent")["matches"], [])

    def test_navigation_rejects_oversized_file_before_reading_it(self):
        self.write_source("x" * 524289)
        for operation in (lambda: self.evolution.inspect(), lambda: self.evolution.search("x")):
            with self.assertRaisesRegex(ValueError, "size limit"):
                operation()

    def test_invalid_parameters_are_rejected_before_snapshot(self):
        with patch.object(self.evolution, "_snapshot", side_effect=AssertionError("Must validate before scanning")):
            for args in ({"path": "../private.py"}, {"path": "/private.py"}, {"path": []},
                         {"offset": True, "path": "src/marka/sample.py"}, {"offset": -1},
                         {"start_line": True}, {"start_line": 3, "end_line": 2}, {"end_line": 201},
                         {"path": "src/marka/sample.py", "expected_sha256": "bad"}, {"offset": 0}):
                with self.subTest(inspect=args), self.assertRaises(ValueError):
                    self.evolution.inspect(**args)
            for args in ({"query": ""}, {"query": "x" * 201}, {"query": "a\nb"}, {"query": "\x00"},
                         {"query": "x", "path": "../private.py"}, {"query": "x", "path": []},
                         {"query": "x", "limit": True}, {"query": "x", "limit": 0}, {"query": "x", "limit": 51}):
                with self.subTest(search=args), self.assertRaises(ValueError):
                    self.evolution.search(**args)


if __name__ == "__main__":
    unittest.main()
