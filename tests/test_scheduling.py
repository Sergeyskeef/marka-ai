"""Calendar boundaries and actual durable scheduling, independent of model guesses."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from marka.config import Settings
from marka.engine import Engine
from marka.queue import Queue
from marka.scheduling import clock_context, owner_timezone, schedule_due
from marka.store import Store
from marka.tools import Tools, ToolInputError


NOW = datetime(2026, 9, 18, 22, 30, tzinfo=timezone.utc).timestamp()


class TimeContextTests(unittest.TestCase):
    def test_owner_date_is_next_day_and_refreshed_between_decisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = Settings(Path(temporary), timezone="UTC+03:00", semantic_search=False)
            settings.prepare()
            store, queue = Store(settings.database), Queue(settings.database)
            job_id = queue.enqueue("Когда завтра?", 17)
            engine = Engine(settings, store, queue, None)
            with patch("marka.scheduling.time.time", return_value=NOW):
                prompt = engine.prompt(queue.get(job_id), [])
            self.assertIn('"local": "2026-09-19T01:30:00+03:00"', prompt)
            with patch("marka.scheduling.time.time", return_value=NOW + 86400):
                next_prompt = engine.prompt(queue.get(job_id), [])
            self.assertIn('"local": "2026-09-20T01:30:00+03:00"', next_prompt)

    def test_timezone_persistence_validation_and_dst(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = Settings(Path(temporary), timezone="UTC-03:30")
            settings.save()
            self.assertEqual(Settings.load(temporary).timezone, "UTC-03:30")
            with patch.dict("os.environ", {"MARKA_TIMEZONE": "UTC+15:00"}):
                with self.assertRaises(ValueError):
                    Settings.load(temporary)
        for zone in (None, "", "../../etc/passwd", "UTC+13:60", "UTC-14:01"):
            with self.subTest(zone=zone), self.assertRaises(ValueError):
                owner_timezone(zone)
        try:
            ZoneInfo("Europe/Berlin")
        except ZoneInfoNotFoundError:
            self.skipTest("IANA database absent; fixed offsets remain supported")
        winter = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
        summer = datetime(2026, 7, 1, tzinfo=timezone.utc).timestamp()
        self.assertTrue(clock_context("Europe/Berlin", now=winter)["local"].endswith("+01:00"))
        self.assertTrue(clock_context("Europe/Berlin", now=summer)["local"].endswith("+02:00"))

    def test_invalid_or_ambiguous_dates_do_not_silently_roll_forward(self):
        values = ["2026-09-19T09:00:00", "2026-09-19", "2026-02-30T09:00:00Z",
                  "2026-09-19T09:00:00-00:00", "2026-09-19T09:00:00+03:60",
                  "2026-09-18T21:00:00Z", "2028-01-01T00:00:00Z", True]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                schedule_due({"due_at": value}, now=NOW)
        for args in ({}, {"due_at": "2026-09-19T09:00:00Z", "delay_seconds": 60},
                     *({"delay_seconds": x} for x in (True, 1.5, "60", 0, -1, 31622401, 10 ** 400))):
            with self.subTest(args=args), self.assertRaises(ValueError):
                schedule_due(args, now=NOW)


class ScheduleQueueTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.settings = Settings(Path(self.temporary.name), timezone="UTC+03:00")
        self.settings.prepare()
        self.store, self.queue = Store(self.settings.database), Queue(self.settings.database)
        self.tools = Tools(self.settings, self.store, self.queue)
        self.identifier = self.queue.enqueue("Напомни завтра в девять", 17)
        self.job = self.queue.get(self.identifier)

    async def call(self, args, step=1):
        return await self.tools.call("task.schedule", args, self.job, [], step)

    async def test_absolute_time_survives_restart_and_fires_at_the_correct_utc_instant(self):
        with patch("marka.tools.time.time", return_value=NOW):
            result = await self.call({"prompt": "Проверить отчёт", "due_at": "2026-09-19T09:00:00+03:00"})
        self.assertEqual(result["due_at"], "2026-09-19T06:00:00+00:00")
        self.assertEqual(result["local_time"], "2026-09-19T09:00:00+03:00")
        restored = Queue(self.settings.database)
        restored.cancel(self.identifier)
        due = restored.get(result["task_id"])["due"]
        with patch("marka.queue.time.time", return_value=due - 0.01):
            self.assertIsNone(restored.claim())
        with patch("marka.queue.time.time", return_value=due):
            self.assertEqual(restored.claim()["id"], result["task_id"])

    async def test_duplicate_receipt_reports_original_due_instead_of_rescheduling(self):
        with patch("marka.tools.time.time", return_value=NOW):
            first = await self.call({"prompt": "one", "delay_seconds": 600})
        with patch("marka.tools.time.time", return_value=NOW + 30):
            repeated = await self.call({"prompt": "one", "delay_seconds": 600})
        self.assertEqual(first["task_id"], repeated["task_id"])
        self.assertEqual(first["due_at"], repeated["due_at"])
        self.assertEqual(repeated["delay_seconds"], 570)
        self.assertEqual(len(self.queue.list()), 2)

    async def test_absolute_schedule_replay_after_its_due_returns_original_receipt(self):
        args = {"prompt": "one", "due_at": "2026-09-19T09:00:00+03:00"}
        with patch("marka.tools.time.time", return_value=NOW):
            first = await self.call(args)
        with patch("marka.tools.time.time", return_value=NOW + 86400):
            repeated = await self.call(args)
        self.assertEqual(first["task_id"], repeated["task_id"])
        self.assertEqual(first["due_at"], repeated["due_at"])
        self.assertEqual(repeated["delay_seconds"], 0)
        self.assertEqual(len(self.queue.list()), 2)

    async def test_many_schedule_and_delivery_actions_keep_distinct_receipts_after_compaction(self):
        class Provider:
            calls = 0

            async def complete(self, prompt, schema):
                self.calls += 1
                if self.calls > 40:
                    return {"kind": "final", "tool": "", "arguments": "{}", "message": "done",
                            "outcome": "completed", "lesson": ""}
                even = self.calls % 2 == 0
                args = ({"path": "report.txt", "caption": str(self.calls)} if even else
                        {"prompt": "task " + str(self.calls), "delay_seconds": 3600})
                return {"kind": "tool", "tool": "workspace.send" if even else "task.schedule",
                        "arguments": json.dumps(args), "message": "", "outcome": "completed", "lesson": ""}

        self.settings.max_steps = 12
        self.settings.semantic_search = False
        self.settings.workspace.joinpath("report.txt").write_text("checked", encoding="utf-8")
        self.queue.configure_task(self.identifier, max_steps=45, max_model_calls=45, max_seconds=900)
        engine = Engine(self.settings, self.store, self.queue, Provider())
        while self.queue.get(self.identifier)["state"] == "queued":
            claimed = self.queue.claim()
            self.assertEqual(claimed["id"], self.identifier)
            await engine.run(claimed)
        self.assertEqual(self.queue.get(self.identifier)["state"], "completed")
        self.assertEqual(self.queue.progress(self.identifier)["budget"]["used"]["model_calls"], 41)
        self.assertEqual(len([row for row in self.queue.list(100) if row["kind"] == "scheduled"]), 20)
        with self.queue.connection() as db:
            deliveries = db.execute("SELECT source FROM deliveries WHERE source LIKE 'artifact:%'").fetchall()
            sources = db.execute("SELECT source FROM jobs WHERE kind='scheduled'").fetchall()
        self.assertEqual(len(deliveries), 20)
        self.assertTrue(all(":decision:" in row[0] for row in [*deliveries, *sources]))

    async def test_rejected_schedules_do_not_create_jobs(self):
        for additions in ({"interval_seconds": True}, {"interval_seconds": 10 ** 50},
                          {"runs": True}, {"runs": "2"}, {"runs": 2}, {"prompt": ["bad"]},
                          {"delay_seconds": 0}):
            with self.subTest(additions=additions), self.assertRaises(ToolInputError):
                await self.call({"prompt": "test", "delay_seconds": 60} | additions)
        self.assertEqual(len(self.queue.list()), 1)


if __name__ == "__main__":
    unittest.main()
