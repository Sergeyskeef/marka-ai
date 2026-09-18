"""Exercise the provider with a real subprocess, without account credentials."""

import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from marka.provider import CodexProvider, ProviderError
from marka.media import validate_image
from image_fixtures import png, JPEG


SCHEMA = {
    "type": "object", "properties": {"reply": {"type": "string"}},
    "required": ["reply"], "additionalProperties": False,
}
FEATURE_NAMES = """shell_tool unified_exec apps plugins remote_plugin browser_use
computer_use image_generation multi_agent hooks memories goals code_mode
code_mode_host workspace_dependencies tool_suggest""".split()


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="marka-provider-test-")
        self.directory = Path(self.temporary.name)
        self.script = self.directory / "fake_codex.py"
        self.record = self.directory / "record.json"
        self.home = self.directory / "auth-home"
        self.home.mkdir()
        self._write_fake()
        real_create = asyncio.create_subprocess_exec

        async def create(*args, **kwargs):
            if Path(args[0]).resolve() == Path(sys.executable).resolve():
                return await real_create(sys.executable, str(self.script), *args[1:], **kwargs)
            return await real_create(*args, **kwargs)

        self.process_patch = patch("marka.provider.asyncio.create_subprocess_exec", side_effect=create)
        self.which_patch = patch("marka.provider.shutil.which", return_value=sys.executable)
        self.process_patch.start()
        self.which_patch.start()
        self.addCleanup(self.process_patch.stop)
        self.addCleanup(self.which_patch.stop)
        self.addCleanup(self.temporary.cleanup)

    def _write_fake(self, version="0.144.1", login="Logged in using ChatGPT"):
        self.script.write_text(
            "import json,os,pathlib,sys,time,hashlib\n"
            "sys.stdin.reconfigure(encoding='utf-8')\n"
            "args=sys.argv[1:]\n"
            f"record=pathlib.Path({str(self.record)!r})\n"
            "if args==['--version']:\n"
            f" print('codex-cli {version}');sys.exit(0)\n"
            "if args==['exec','--help']:\n"
            " print('--ignore-user-config --ignore-rules --ephemeral --output-schema');sys.exit(0)\n"
            "if args==['features','list']:\n"
            f" print('\\n'.join(x+' stable true' for x in {FEATURE_NAMES!r}));sys.exit(0)\n"
            "if args==['login','status']:\n"
            f" print({login!r},file=sys.stderr);sys.exit(0)\n"
            "prompt=sys.stdin.read()\n"
            "images=[pathlib.Path(args[i+1]) for i,x in enumerate(args) if x=='--image']\n"
            "record.write_text(json.dumps({'args':args,'env':dict(os.environ),'prompt':prompt,'cwd':os.getcwd(),'pid':os.getpid(),'images':[{'path':str(p),'bytes':len(p.read_bytes()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in images]}))\n"
            "if prompt=='timeout': time.sleep(10)\n"
            "if prompt=='secret-error':\n"
            " print('401 my-bot-token and PRIVATE PROMPT',file=sys.stderr);sys.exit(1)\n"
            "if prompt=='overflow':\n"
            " sys.stdout.write('x'*1200000);sys.stdout.flush();time.sleep(10)\n"
            "output=pathlib.Path(args[args.index('--output-last-message')+1])\n"
            "if prompt=='malformed': output.write_text('{')\n"
            "elif prompt=='array': output.write_text('[]')\n"
            "elif prompt=='large': output.write_text(json.dumps({'reply':'x'*300000}))\n"
            "else: output.write_text(json.dumps({'reply':'Hello, Сергей'}),encoding='utf-8')\n"
            "if prompt=='native-tool': print(json.dumps({'type':'item.completed','item':{'type':'mcp_tool_call'}}))\n"
            "print(json.dumps({'type':'turn.completed'}))\n",
            encoding="utf-8",
        )

    def provider(self, timeout=10):
        return CodexProvider(home=self.home, model="gpt-5.6-sol", timeout=timeout)

    async def test_structured_subprocess_uses_stdin_no_secrets_or_native_tools(self):
        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "secret-tg", "OPENAI_API_KEY": "secret-api",
            "CODEX_API_KEY": "secret-codex", "CODEX_ACCESS_TOKEN": "secret-access",
            "GITHUB_TOKEN": "secret-gh", "CUSTOM_SECRET": "secret-custom",
        }):
            result = await self.provider().complete("Привет, Марк", SCHEMA)
        self.assertEqual(result, {"reply": "Hello, Сергей"})
        record = json.loads(self.record.read_text())
        self.assertEqual(record["prompt"], "Привет, Марк")
        self.assertNotIn("Привет, Марк", record["args"])
        for key in ("TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY",
                    "CODEX_ACCESS_TOKEN", "GITHUB_TOKEN", "CUSTOM_SECRET"):
            self.assertNotIn(key, record["env"])
        self.assertEqual(record["env"]["CODEX_HOME"], str(self.home.resolve()))
        self.assertNotEqual(record["env"]["HOME"], str(self.home))
        self.assertFalse(Path(record["cwd"]).exists())
        args = record["args"]
        for feature in FEATURE_NAMES:
            self.assertIn(["--disable", feature], [args[i:i+2] for i in range(len(args)-1)])
        self.assertIn('web_search="disabled"', args)
        self.assertIn("tools.view_image=false", args)
        self.assertIn("read-only", args)

    async def test_status_contains_only_safe_account_metadata(self):
        self.assertEqual(await self.provider().status(), {
            "version": "0.144.1", "authenticated": True, "auth_method": "chatgpt",
        })
        self._write_fake(version="0.154.0-alpha.6.2")
        self.assertEqual((await self.provider().status())["version"], "0.154.0-alpha.6.2")

    async def test_images_are_copied_to_isolated_temp_and_all_tool_guards_remain(self):
        images = [validate_image(png()), validate_image(JPEG)]
        await self.provider().complete("Describe these images", SCHEMA, images=images)
        record = json.loads(self.record.read_text())
        self.assertEqual([item["sha256"] for item in record["images"]], [image.sha256 for image in images])
        self.assertEqual(len(record["images"]), 2)
        for item in record["images"]:
            self.assertEqual(Path(item["path"]).parent, Path(record["cwd"]))
            self.assertFalse(Path(item["path"]).exists(), "Temporary image bytes must be removed")
        self.assertIn("tools.view_image=false", record["args"])
        self.assertIn("--output-schema", record["args"])
        self.assertIn("--ignore-user-config", record["args"])
        self.assertIn("--ignore-rules", record["args"])
        self.assertEqual(record["args"][-1], "-")

    async def test_images_cannot_enable_native_tools_or_accept_filesystem_paths(self):
        with self.assertRaisesRegex(ValueError, "never filesystem paths"):
            await self.provider().complete("read secret", SCHEMA, images=[self.home / "auth.json"])
        self.assertFalse(self.record.exists())
        with self.assertRaisesRegex(ProviderError, "native tool"):
            await self.provider().complete("native-tool", SCHEMA, images=[validate_image(png())])

    async def test_cancelling_image_inference_removes_temp_image(self):
        task = asyncio.create_task(self.provider().complete("timeout", SCHEMA, images=[validate_image(png())]))
        for _ in range(200):
            if self.record.exists():
                break
            await asyncio.sleep(0.01)
        self.assertTrue(self.record.exists())
        record = json.loads(self.record.read_text())
        self.assertTrue(Path(record["images"][0]["path"]).exists())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(Path(record["images"][0]["path"]).exists())

    async def test_api_key_login_is_refused(self):
        self._write_fake(login="Logged in using an API key")
        with self.assertRaisesRegex(ProviderError, "ChatGPT login"):
            await self.provider().complete("hello", SCHEMA)
        self.assertFalse(self.record.exists())

    async def test_old_cli_is_refused_before_inference(self):
        self._write_fake(version="0.130.0")
        with self.assertRaisesRegex(ProviderError, "0.144.1"):
            await self.provider().complete("hello", SCHEMA)
        self.assertFalse(self.record.exists())

    async def test_errors_never_return_raw_secret_or_prompt(self):
        with self.assertRaises(ProviderError) as caught:
            await self.provider().complete("secret-error", SCHEMA)
        self.assertIn("authentication", str(caught.exception))
        self.assertNotIn("my-bot-token", str(caught.exception))
        self.assertNotIn("PRIVATE PROMPT", str(caught.exception))

    async def test_invalid_or_excessive_structured_outputs_fail(self):
        for prompt in ("malformed", "array", "large", "native-tool"):
            with self.subTest(prompt=prompt):
                with self.assertRaises(ProviderError):
                    await self.provider().complete(prompt, SCHEMA)

    async def test_timeout_terminates_process(self):
        with self.assertRaisesRegex(ProviderError, "timed out"):
            await self.provider(timeout=0.2).complete("timeout", SCHEMA)
        self.assertTrue(self.record.exists())

    async def test_output_overflow_is_bounded(self):
        with self.assertRaisesRegex(ProviderError, "output exceeded"):
            await self.provider().complete("overflow", SCHEMA)

    async def test_cancellation_stops_running_inference(self):
        task = asyncio.create_task(self.provider().complete("timeout", SCHEMA))
        for _ in range(200):
            if self.record.exists():
                break
            await asyncio.sleep(0.01)
        self.assertTrue(self.record.exists())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_input_limits_fail_before_starting_cli(self):
        with self.assertRaises(ValueError):
            await self.provider().complete("", SCHEMA)
        with self.assertRaises(ValueError):
            await self.provider().complete("hello", {"type": "array"})
        with self.assertRaisesRegex(ProviderError, "Prompt exceeded"):
            await self.provider().complete("x" * 1_048_577, SCHEMA)
        self.assertFalse(self.record.exists())


if __name__ == "__main__":
    unittest.main()
