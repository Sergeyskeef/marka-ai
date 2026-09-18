import socket
from datetime import datetime
import hashlib
import unittest
from unittest.mock import patch

from marka.web import PublicHTTPS, TextOnly, download, fetch, search


class WebBoundaryTests(unittest.TestCase):
    def test_unsafe_urls_fail_before_network(self):
        with patch("socket.getaddrinfo") as resolver:
            for url in ("http://example.com", "https://u:p@example.com", "https://example.com:8443", "file:///etc/passwd", "https://example.com/\nX"):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    download(url)
            resolver.assert_not_called()

    def test_private_mixed_and_multicast_answers_never_connect(self):
        for addresses in (("127.0.0.1",), ("93.184.215.14", "10.0.0.1"), ("169.254.169.254",), ("224.0.0.1",), ("::1",)):
            records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses]
            with self.subTest(addresses=addresses), patch("socket.getaddrinfo", return_value=records), patch("socket.socket") as raw:
                with self.assertRaises(ValueError):
                    PublicHTTPS("example.com").connect()
                raw.assert_not_called()

    def test_html_scripts_and_styles_are_not_context(self):
        parser = TextOnly()
        parser.feed('<h1>Title</h1><script>steal()</script><style>hidden</style><p>Actual evidence</p>')
        self.assertEqual(parser.parts, ["Title", "Actual evidence"])

    def test_long_source_can_be_reassembled_with_pinned_raw_hash(self):
        original = "Длинный проверяемый источник.\n" * 1500
        body = original.encode("utf-8")
        expected = hashlib.sha256(body).hexdigest()
        pieces, offset = [], 0
        with patch("marka.web.download", return_value=(body, "text/plain; charset=utf-8", "https://example.org/final")):
            while True:
                page = fetch("https://example.org/start", offset, expected)
                self.assertEqual(page["sha256"], expected)
                self.assertLessEqual(len(page["content"]), 14000)
                self.assertEqual(page["total_chars"], len(original))
                self.assertEqual(page["url"], "https://example.org/final")
                self.assertIsNotNone(datetime.fromisoformat(page["fetched_at"]).tzinfo)
                pieces.append(page["content"])
                if page["next_offset"] is None:
                    break
                offset = page["next_offset"]
        self.assertEqual("".join(pieces), original)

    def test_changed_source_is_rejected_instead_of_mixing_pages(self):
        with patch("marka.web.download", side_effect=[(b"first", "text/plain", "https://example.org"),
                                                       (b"second", "text/plain", "https://example.org")]):
            first = fetch("https://example.org")
            with self.assertRaisesRegex(ValueError, "changed"):
                fetch("https://example.org", 2, first["sha256"])

    def test_invalid_page_parameters_do_not_download(self):
        with patch("marka.web.download") as downloader:
            for kwargs in ({"offset": -1}, {"offset": True}, {"offset": "1"},
                           {"expected_sha256": "not-a-hash"}, {"expected_sha256": None}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    fetch("https://example.org", **kwargs)
            downloader.assert_not_called()

    def test_html_keeps_only_bounded_valid_absolute_https_links(self):
        html = ('<script><a href="https://bad.example/">hidden</a></script>'
                '<a href="../facts">Useful <b>source</b></a><a href="../facts">Duplicate</a>'
                '<a href="http://example.org/">HTTP</a><a href="javascript:alert(1)">JS</a>'
                '<a href="https://u:p@example.org/">Credentials</a><a href="https://[broken/">Broken</a>'
                '<a href="https://example.org:bad/">Invalid port</a><a href="https://exa mple.org/">Bad host</a>'
                '<a href="/bad&#10;control">Control</a>' + ''.join(f'<a href="/page/{n}">Page{n}</a>' for n in range(50)))
        with patch("marka.web.download", return_value=(html.encode(), "TEXT/HTML; Charset=UTF-8", "https://example.org/docs/index")):
            page = fetch("https://example.org/docs/index")
        self.assertEqual(len(page["links"]), 30)
        self.assertEqual(page["links"][0], {"url": "https://example.org/facts", "text": "Useful source"})
        self.assertTrue(all(item["url"].startswith("https://example.org/") for item in page["links"]))
        self.assertNotIn("hidden", page["content"])
        self.assertEqual(page["sha256"], hashlib.sha256(html.encode()).hexdigest())

    def test_declared_charset_and_invalid_charset_fallback(self):
        original = "Русский источник"
        for payload, content_type, expected in ((original.encode("cp1251"), 'text/plain; charset="windows-1251"', original),
                                                 (original.encode(), "text/plain; charset=unknown-charset", original),
                                                 (original.encode(), "text/plain", original)):
            with self.subTest(content_type=content_type), patch("marka.web.download", return_value=(payload, content_type, "https://example.org")):
                self.assertEqual(fetch("https://example.org")["content"], expected)

    def test_long_link_urls_cannot_overwhelm_the_source_page(self):
        html = ''.join(f'<a href="https://example.org/{number}/' + 'x' * 3000 + '">Link</a>' for number in range(30))
        with patch("marka.web.download", return_value=(html.encode(), "text/html", "https://example.org")):
            page = fetch("https://example.org")
        self.assertLessEqual(sum(len(link["url"]) for link in page["links"]), 6000)

    def test_malformed_search_xml_is_an_observed_value_error(self):
        with patch("marka.web.download", return_value=(b"<html>not RSS", "text/html", "https://www.bing.com/")):
            with self.assertRaisesRegex(ValueError, "invalid XML"):
                search("sample")

    def test_download_size_cap_and_redirect_policy_remain_effective(self):
        class Response:
            status = 200
            def getheader(self, name, default=""):
                return "text/plain" if name == "Content-Type" else default
            def read1(self, size):
                return b"x" * size
        with patch("marka.web.PublicHTTPS") as connection:
            connection.return_value.getresponse.return_value = Response()
            with self.assertRaisesRegex(ValueError, "512 KiB"):
                download("https://example.org/large")
            connection.return_value.close.assert_called_once()
        class Redirect(Response):
            status = 302
            def getheader(self, name, default=""):
                return "http://127.0.0.1/private" if name == "Location" else default
        with patch("marka.web.PublicHTTPS") as connection:
            connection.return_value.getresponse.return_value = Redirect()
            with self.assertRaises(ValueError):
                download("https://example.org/redirect")
            self.assertEqual(connection.call_count, 1)


if __name__ == "__main__":
    unittest.main()
