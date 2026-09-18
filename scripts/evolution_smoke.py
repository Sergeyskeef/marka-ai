#!/usr/bin/env python3
"""Exercise code evolution with the real runner and an explicitly fake token.

The current installed redactor does not handle Slack bot tokens. This fixture
tests a candidate that adds that behavior without installing it. Both runs use
the same shipped tests plus the same supplied regression case. No LLM/auth is
involved, and a passing case makes no claim of broader agent improvement.
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import tempfile

from marka.config import Settings
from marka.evolution import Evolution
from marka.tools import Workspace
import marka.redact


async def smoke() -> dict:
    source = Path(marka.redact.__file__)
    before = source.read_bytes()
    original = before.decode("utf-8").replace("\r\n", "\n")
    insertion = '    (re.compile(r"\\bxoxb-[A-Za-z0-9-]{16,}\\b"), "[REDACTED_SLACK_TOKEN]"),\n'
    candidate = original.replace("_PATTERNS = (\n", "_PATTERNS = (\n" + insertion, 1)
    if candidate == original:
        raise RuntimeError("The redactor fixture no longer matches the installed source")
    regression = '''import unittest
from marka.redact import redact
class SlackRedactionRegression(unittest.TestCase):
    def test_fake_slack_bot_token_is_redacted(self):
        token = "xoxb-" + "000000000000-000000000000-FAKENOTAREALSECRET012345"
        self.assertEqual(redact("value=" + token), "value=[REDACTED_SLACK_TOKEN]")
'''
    with tempfile.TemporaryDirectory(prefix="marka-evolution-smoke-") as directory:
        settings = Settings(Path(directory), sandbox_socket=os.environ.get(
            "MARKA_SANDBOX_SOCKET", "/run/marka/runner.sock"))
        workspace = Workspace(settings.workspace)
        evolution = Evolution(settings, workspace)
        result = await evolution.experiment(
            "Regression fixture: redact explicitly fake Slack bot token without changing other redaction behavior",
            {"src/marka/redact.py": candidate}, regression,
        )
        report_path = settings.data_dir / "evolution" / result["id"] / "report.json"
        report = json.loads(report_path.read_text("utf-8"))
        assert result["status"] == "improved_on_provided_case", json.dumps({
            "result": result,
            "baseline_failures": report["baseline"].get("failures"),
            "candidate_failures": report["candidate"].get("failures"),
        })
        assert result["promotion"] == "none"
        assert result["baseline_tests"] == result["candidate_tests"]
        assert len(result["improved_tests"]) == 1
        assert report["baseline"]["discovered_sha256"] == report["candidate"]["discovered_sha256"]
        assert report["baseline"]["test_integrity"] and report["candidate"]["test_integrity"]
        assert report["baseline"]["source_integrity"] and report["candidate"]["source_integrity"]
        assert (workspace.root / result["patch_path"]).is_file()
        assert source.read_bytes() == before, "Installed runtime must remain unchanged"
        return {
            "ok": True, "status": result["status"], "promotion": result["promotion"],
            "baseline_tests": result["baseline_tests"], "candidate_tests": result["candidate_tests"],
            "improved_tests": result["improved_tests"], "tests_sha256": report["tests_sha256"],
            "installed_source_sha256": hashlib.sha256(before).hexdigest(),
            "installed_source_unchanged": True, "limitation": result["limitation"],
        }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(smoke())))
