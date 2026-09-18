from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from marka.telegram import (HTTPResponse, TelegramClient,
                            TelegramError, TelegramRetryAfter, parse_message,
                            split_message, valid_private_message)


TOKEN = "123456:" + "fake-token-for-tests-only-12345678"


def response(result=None, *, status=200, **extra):
    data = {"ok": status == 200, "result": result, **extra}
    return HTTPResponse(status, json.dumps(data).encode())


class FakeHTTP:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def update(**changes):
    raw = {"update_id": 41, "message": {"message_id": 2,
           "from": {"id": 17, "is_bot": False},
           "chat": {"id": 17, "type": "private"}, "text": "Привет"}}
    raw["message"].update(changes)
    return raw


class ParseTests(unittest.TestCase):
    def test_private_human_message(self):
        parsed = parse_message(update())
        self.assertEqual((parsed.update_id, parsed.user_id, parsed.text), (41, 17, "Привет"))
        self.assertTrue(valid_private_message(parsed))

    def test_untrusted_envelopes_are_rejected(self):
        cases = [update(forward_origin={}), update(forward_date=1),
                 update(via_bot={"id": 2}), update(sender_chat={}),
                 update(**{"from": {"id": 17, "is_bot": True}}),
                 update(chat={"id": -20, "type": "channel"}),
                 update(text=None), update(text=""), {"update_id": 5, "edited_message": {}}]
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertIsNone(parse_message(raw))

    def test_mismatched_sender_and_group_are_not_private(self):
        self.assertFalse(valid_private_message(parse_message(update(chat={"id": 18, "type": "private"}))))
        self.assertFalse(valid_private_message(parse_message(update(chat={"id": -18, "type": "group"}))))

    def test_malformed_untrusted_json_does_not_crash(self):
        for value in [None, 4, [], {}, {"update_id": True}, update(**{"from": []}), update(chat=[]), update(text=7)]:
            self.assertIsNone(parse_message(value))

    def test_utf16_chunks_preserve_entire_text(self):
        text = "А" * 3499 + "🙂" * 2500 + "\n끝"
        chunks = split_message(text)
        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(len(part.encode("utf-16-le")) // 2 <= 3500 for part in chunks))
        self.assertEqual(chunks[0], "А" * 3499)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_polling_protocol_and_bot_identity(self):
        fake = FakeHTTP(response({"id": 3, "is_bot": True}), response([update()]))
        client = TelegramClient(TOKEN, transport=fake)
        self.assertEqual((await client.get_me())["id"], 3)
        self.assertEqual(len(await client.get_updates(42, timeout=40)), 1)
        payload = json.loads(fake.requests[1][0].data)
        self.assertEqual(payload, {"offset": 42, "timeout": 40, "limit": 100, "allowed_updates": ["message"]})
        self.assertGreaterEqual(fake.requests[1][1], 45)

    async def test_send_is_plain_text_and_chunked(self):
        fake = FakeHTTP(response({"message_id": 1}), response({"message_id": 2}))
        client = TelegramClient(TOKEN, transport=fake)
        text = "<b>literal</b>" + "🙂" * 2000
        self.assertEqual(await client.send_message(17, text), [1, 2])
        payloads = [json.loads(item[0].data) for item in fake.requests]
        self.assertEqual("".join(item["text"] for item in payloads), text)
        self.assertTrue(all("parse_mode" not in item for item in payloads))

    async def test_timeout_is_uncertain_without_retry_or_secret(self):
        fake = FakeHTTP(urllib.error.URLError("https://api.telegram.org/bot" + TOKEN))
        client = TelegramClient(TOKEN, transport=fake)
        with self.assertRaises(TelegramError) as caught:
            await client.send_message(17, "hello")
        self.assertTrue(caught.exception.uncertain)
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertEqual(len(fake.requests), 1)

    async def test_polling_failure_is_not_send_uncertainty(self):
        client = TelegramClient(TOKEN, transport=FakeHTTP(TimeoutError(TOKEN)))
        with self.assertRaises(TelegramError) as caught:
            await client.get_updates(0)
        self.assertFalse(caught.exception.uncertain)

    async def test_permanent_and_rate_limit_errors_have_safe_messages(self):
        for code in [400, 401, 403, 409]:
            with self.subTest(code=code):
                client = TelegramClient(TOKEN, transport=FakeHTTP(response(status=code, error_code=code, description=TOKEN)))
                with self.assertRaises(TelegramError) as caught:
                    await client.get_updates(0)
                self.assertEqual(caught.exception.code, code)
                self.assertTrue(caught.exception.permanent)
                self.assertNotIn(TOKEN, str(caught.exception))
        client = TelegramClient(TOKEN, transport=FakeHTTP(response(status=429, error_code=429, parameters={"retry_after": 23})))
        with self.assertRaises(TelegramRetryAfter) as caught:
            await client.send_message(17, "hello")
        self.assertEqual(caught.exception.seconds, 23)
        self.assertFalse(caught.exception.uncertain)

    async def test_partial_send_preserves_receipts(self):
        client = TelegramClient(TOKEN, transport=FakeHTTP(response({"message_id": 22}), TimeoutError()))
        with self.assertRaises(TelegramError) as caught:
            await client.send_message(17, "a" * 4000)
        self.assertEqual(caught.exception.sent_message_ids, [22])
        self.assertTrue(caught.exception.uncertain)

    async def test_invalid_send_receipt_is_uncertain(self):
        for reply in [HTTPResponse(200, b"<html>invalid</html>"), response({}), response({"message_id": True})]:
            client = TelegramClient(TOKEN, transport=FakeHTTP(reply))
            with self.assertRaises(TelegramError) as caught:
                await client.send_message(17, "hello")
            self.assertTrue(caught.exception.uncertain)

    async def test_document_multipart_and_size_bound(self):
        fake = FakeHTTP(response({"message_id": 9}))
        client = TelegramClient(TOKEN, transport=fake)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.txt"
            path.write_bytes(b"bounded report content")
            self.assertEqual(await client.send_document(17, path, "Report"), 9)
            request = fake.requests[0][0]
            self.assertIn('multipart/form-data; boundary=', request.get_header('Content-type'))
            self.assertIn(b'name="document"; filename="report.txt"', request.data)
            self.assertIn(b"bounded report content", request.data)
            self.assertNotIn(str(path.parent).encode(), request.data)
            # Exercise the same size boundary within the runner's file quota.
            with patch("marka.telegram.MAX_DOCUMENT_BYTES", 1024):
                with path.open("wb") as stream:
                    stream.truncate(1025)
                with self.assertRaises(TelegramError):
                    await client.send_document(17, path)
            self.assertEqual(len(fake.requests), 1)

    async def test_no_token_in_configuration_errors(self):
        for token in ["", "bad token", "https://host/secret"]:
            with self.assertRaises(TelegramError):
                TelegramClient(token)
        for base in ["http://api.telegram.org", "https://example.org/path", "https://x:y@example.org"]:
            with self.assertRaises(TelegramError):
                TelegramClient(TOKEN, api_base=base)


if __name__ == "__main__":
    unittest.main()
