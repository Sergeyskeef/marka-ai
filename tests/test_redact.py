import json
import unittest

from marka.redact import redact, redact_value


class RedactionTests(unittest.TestCase):
    def test_canonical_json_stays_parseable_after_recursive_and_repeated_redaction(self):
        raw = {"ok": True, "result": {"content": 'password=fake_value\nпароль: fake_russian',
                                    "password": "fake_json_value"}}
        encoded = json.dumps(redact_value(raw), ensure_ascii=False)
        saved = redact(encoded)
        result = json.loads(saved)
        self.assertTrue(result["ok"])
        self.assertNotIn("fake_value", saved)
        self.assertNotIn("fake_russian", saved)
        self.assertNotIn("fake_json_value", saved)
        self.assertEqual(redact(saved), saved)

    def test_service_keys_headers_and_url_credentials(self):
        examples = ["xoxb-" + "0000000000-FAKE00000000", "glpat-" + "FAKE"*8,
                    "Bearer " + "FAKE"*8, "https://fakeuser:fakepassword@example.test/path"]
        for value in examples:
            with self.subTest(kind=value[:6]):
                self.assertNotEqual(redact(value), value)
                self.assertNotIn("FAKE", redact(value))
                self.assertNotIn("fakepassword", redact(value))

    def test_normal_russian_prose_is_not_a_password_assignment(self):
        value = "Пароль нужно хранить отдельно. Токены контекста помогают оценить размер."
        self.assertEqual(redact(value), value)
