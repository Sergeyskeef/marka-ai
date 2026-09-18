from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from marka.telegram import (HTTPResponse, TelegramClient,
                            TelegramError, TelegramRetryAfter, parse_message,
                            split_message, valid_private_message, parse_attachment,
                            attachment_problem, decode_text_attachment, MAX_ATTACHMENT_BYTES,
                            _http_request, _NoRedirect)


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


def document_update(**changes):
    raw = update(text=None, caption="Проверь этот файл", document={
        "file_id": "FILE_ID_1", "file_unique_id": "UNIQUE_1", "file_name": "report.txt",
        "mime_type": "text/plain", "file_size": 5,
    })
    raw["message"]["document"].update(changes)
    return raw


class AttachmentParsingTests(unittest.TestCase):
    def test_original_private_document_metadata_and_caption(self):
        item = parse_attachment(document_update())
        self.assertEqual((item.update_id, item.chat_id, item.user_id), (41, 17, 17))
        self.assertEqual(item.file_name, "report.txt")
        self.assertEqual(item.caption, "Проверь этот файл")
        self.assertTrue(valid_private_message(item))
        self.assertIsNone(attachment_problem(item))
        self.assertEqual(decode_text_attachment(item, b"hello"), "hello")

    def test_forwarded_edited_bot_group_mismatched_and_malformed_inputs_rejected(self):
        examples = []
        for key, value in (("forward_origin", {}), ("forward_date", 1), ("via_bot", {}),
                           ("sender_chat", {}), ("from", {"id": 17, "is_bot": True}),
                           ("chat", {"id": -17, "type": "group"}),
                           ("chat", {"id": 18, "type": "private"}),
                           ("chat", {"id": 17, "type": []})):
            raw = document_update()
            raw["message"][key] = value
            examples.append(raw)
        raw = document_update()
        raw["edited_message"] = raw.pop("message")
        examples.append(raw)
        examples += [None, [], {"update_id": True}, document_update(file_size=True),
                     document_update(file_size=-1), document_update(file_id="https://elsewhere/"),
                     document_update(file_name="broken\ud800.txt")]
        for raw in examples:
            with self.subTest(raw_type=type(raw).__name__):
                self.assertIsNone(parse_attachment(raw))

    def test_unsupported_and_oversized_files_get_safe_problem_before_download(self):
        self.assertIn("PDF", attachment_problem(parse_attachment(document_update(file_name="report.pdf"))))
        self.assertIn("512 KiB", attachment_problem(parse_attachment(document_update(file_size=MAX_ATTACHMENT_BYTES + 1))))
        self.assertIn("supported", attachment_problem(parse_attachment(document_update(file_name="archive.zip"))))

    def test_filename_is_basename_and_does_not_inject_path(self):
        item = parse_attachment(document_update(file_name="../../private\\settings.txt"))
        self.assertNotIn("/", item.file_name)
        self.assertNotIn("\\", item.file_name)
        self.assertFalse(item.file_name.startswith("."))

    def test_utf8_bom_unknown_size_and_binary_rejection(self):
        item = parse_attachment(document_update(file_size=None, file_name="script.py"))
        self.assertEqual(decode_text_attachment(item, b"\xef\xbb\xbfprint('hello')"), "print('hello')")
        for payload in (b"not utf8\xff", b"binary\x00payload", b"escape\x1bpayload", b"x" * (MAX_ATTACHMENT_BYTES + 1)):
            with self.assertRaises(TelegramError):
                decode_text_attachment(item, payload)
        with self.assertRaises(TelegramError):
            decode_text_attachment(parse_attachment(document_update()), b"shorter than declared")


class AttachmentDownloadTests(unittest.IsolatedAsyncioTestCase):
    def metadata(self, **changes):
        return response({"file_id": "FILE_ID_1", "file_path": "documents/file_42.txt", "file_size": 5, **changes})

    async def test_download_uses_getfile_then_same_official_origin_get(self):
        fake = FakeHTTP(self.metadata(), HTTPResponse(200, b"hello"))
        client = TelegramClient(TOKEN, transport=fake)
        self.assertEqual(await client.download_file("FILE_ID_1", expected_size=5), b"hello")
        self.assertEqual(len(fake.requests), 2)
        self.assertTrue(fake.requests[0][0].full_url.endswith("/getFile"))
        self.assertEqual(json.loads(fake.requests[0][0].data), {"file_id": "FILE_ID_1"})
        request = fake.requests[1][0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.full_url, f"https://api.telegram.org/file/bot{TOKEN}/documents/file_42.txt")
        self.assertEqual(request._marka_response_limit, MAX_ATTACHMENT_BYTES)

    async def test_download_refuses_nontelegram_origin_before_getfile(self):
        fake = FakeHTTP()
        client = TelegramClient(TOKEN, api_base="https://example.org", transport=fake)
        with self.assertRaises(TelegramError):
            await client.download_file("FILE_ID_1")
        self.assertFalse(fake.requests)

    async def test_unsafe_getfile_paths_never_reach_download(self):
        for path in ("/documents/file.txt", "//evil.test/file", "https://evil.test/a", "../private",
                     "documents/../auth.json", "documents/%2e%2e/file", "documents/file?x=1",
                     "documents/file#fragment", "documents\\file", "documents//file", "documents/.hidden"):
            fake = FakeHTTP(self.metadata(file_path=path))
            with self.subTest(path=path), self.assertRaises(TelegramError):
                await TelegramClient(TOKEN, transport=fake).download_file("FILE_ID_1")
            self.assertEqual(len(fake.requests), 1)

    async def test_invalid_metadata_and_declared_oversize_stop_before_download(self):
        for changes in ({"file_id": "OTHER_ID"}, {"file_size": MAX_ATTACHMENT_BYTES + 1},
                        {"file_size": True}, {"file_size": -1}, {"file_size": 6}):
            fake = FakeHTTP(self.metadata(**changes))
            with self.subTest(changes=changes), self.assertRaises(TelegramError):
                await TelegramClient(TOKEN, transport=fake).download_file("FILE_ID_1", expected_size=5)
            self.assertEqual(len(fake.requests), 1)

    async def test_actual_payload_and_truncated_body_are_checked(self):
        for data in (b"x" * (MAX_ATTACHMENT_BYTES + 1), b"four", b"sixsix"):
            fake = FakeHTTP(self.metadata(), HTTPResponse(200, data))
            with self.assertRaises(TelegramError):
                await TelegramClient(TOKEN, transport=fake).download_file("FILE_ID_1")

    async def test_missing_optional_size_still_enforces_actual_limit(self):
        fake = FakeHTTP(response({"file_id": "FILE_ID_1", "file_path": "documents/file.txt"}), HTTPResponse(200, b"hello"))
        self.assertEqual(await TelegramClient(TOKEN, transport=fake).download_file("FILE_ID_1"), b"hello")

    async def test_download_redirect_and_network_errors_are_safe_and_not_sends(self):
        for result in (HTTPResponse(302, TOKEN.encode()), HTTPResponse(500, TOKEN.encode()),
                       urllib.error.URLError("https://api.telegram.org/file/bot" + TOKEN)):
            fake = FakeHTTP(self.metadata(), result)
            with self.assertRaises(TelegramError) as caught:
                await TelegramClient(TOKEN, transport=fake).download_file("FILE_ID_1")
            self.assertNotIn(TOKEN, str(caught.exception))
            self.assertFalse(caught.exception.uncertain)
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test"))

    async def test_input_limits_are_checked_before_any_request(self):
        for arguments in ({"expected_size": MAX_ATTACHMENT_BYTES + 1}, {"expected_size": True},
                          {"max_bytes": MAX_ATTACHMENT_BYTES + 1}, {"max_bytes": 0}):
            fake = FakeHTTP()
            with self.assertRaises(TelegramError):
                await TelegramClient(TOKEN, transport=fake).download_file("FILE_ID_1", **arguments)
            self.assertEqual(fake.requests, [])

    def test_default_transport_bounds_actual_read_not_only_buffer_afterwards(self):
        class FileResponse:
            code = 200
            read_limit = None
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit):
                self.read_limit = limit
                return b"x" * limit
        class Opener:
            def open(self, request, timeout): return file_response
        file_response = FileResponse()
        import urllib.request
        request = urllib.request.Request("https://api.telegram.org/file/example")
        request._marka_response_limit = 1024
        with patch("marka.telegram.urllib.request.build_opener", return_value=Opener()):
            with self.assertRaises(ValueError):
                _http_request(request, 5)
        self.assertEqual(file_response.read_limit, 1025)


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
