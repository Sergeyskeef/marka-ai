import socket
import unittest
from unittest.mock import patch

from marka.web import PublicHTTPS, TextOnly, download


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


if __name__ == "__main__":
    unittest.main()
