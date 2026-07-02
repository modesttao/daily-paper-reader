import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from llm import (
    AnthropicClient,
    ClaudeCodeClient,
    DeepSeekClient,
    LLMClient,
    create_summary_client_from_env,
)


def _fake_message(text='{"related": ["a"]}', stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


class _AnthropicStubMixin(unittest.TestCase):
    def setUp(self):
        self._saved_module = sys.modules.get("anthropic")
        self.fake_module = types.ModuleType("anthropic")
        self.sdk_client = MagicMock()
        self.fake_module.Anthropic = MagicMock(return_value=self.sdk_client)
        sys.modules["anthropic"] = self.fake_module

    def tearDown(self):
        if self._saved_module is not None:
            sys.modules["anthropic"] = self._saved_module
        else:
            sys.modules.pop("anthropic", None)

    def _set_final_message(self, message):
        stream_cm = self.sdk_client.messages.stream.return_value
        stream_cm.__enter__.return_value.get_final_message.return_value = message


class AnthropicChatTest(_AnthropicStubMixin):
    def test_chat_maps_messages_and_usage(self):
        self._set_final_message(_fake_message(text="hello"))
        client = AnthropicClient(api_key="sk-ant-test")

        result = client.chat([
            {"role": "system", "content": "you are a helper"},
            {"role": "user", "content": "hi"},
        ])

        self.assertEqual(result["content"], "hello")
        self.assertEqual(result["tokens"], {
            "prompt": 10, "content": 5, "reasoning": 0, "total": 15,
        })
        self.assertEqual(result["refusal"], "")

        params = self.sdk_client.messages.stream.call_args.kwargs
        self.assertEqual(params["model"], "claude-opus-4-8")
        self.assertEqual(params["system"], "you are a helper")
        self.assertEqual(params["messages"], [{"role": "user", "content": "hi"}])
        # Claude 4.7+ 不接受采样参数
        for key in ("temperature", "top_p", "top_k", "frequency_penalty"):
            self.assertNotIn(key, params)
        # 默认 max_tokens（393216）必须被压到 Claude 的输出上限内
        self.assertLessEqual(params["max_tokens"], 64000)

    def test_chat_marks_refusal(self):
        self._set_final_message(_fake_message(text="", stop_reason="refusal"))
        client = AnthropicClient(api_key="sk-ant-test")
        result = client.chat([{"role": "user", "content": "hi"}])
        self.assertTrue(result["refusal"])

    def test_chat_structured_uses_output_config_schema(self):
        self._set_final_message(_fake_message(text='{"related": ["a", "b"]}'))
        client = AnthropicClient(api_key="sk-ant-test")

        schema = {
            "type": "object",
            "properties": {
                "related": {"type": "array", "items": {"type": "string"}},
            },
        }
        result = client.chat_structured(
            [{"role": "user", "content": "give related keywords"}],
            schema_name="related",
            schema=schema,
        )

        self.assertEqual(result["parsed"], {"related": ["a", "b"]})
        self.assertIsNone(result["parse_error"])
        self.assertEqual(result["response_format_used"], "json_schema")

        params = self.sdk_client.messages.stream.call_args.kwargs
        fmt = params["output_config"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        # object 节点需要补全 additionalProperties/required
        self.assertIs(fmt["schema"]["additionalProperties"], False)
        self.assertEqual(fmt["schema"]["required"], ["related"])

    def test_prepare_output_schema_strips_unsupported_keys(self):
        schema = {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "minimum": 1, "maximum": 5},
                "pattern": {"type": "string", "maxLength": 10},
            },
        }
        prepared = AnthropicClient._prepare_output_schema(schema)
        self.assertNotIn("minimum", prepared["properties"]["score"])
        self.assertNotIn("maximum", prepared["properties"]["score"])
        # 名为 pattern 的属性本身不能被误删
        self.assertIn("pattern", prepared["properties"])
        self.assertNotIn("maxLength", prepared["properties"]["pattern"])


class AnthropicFactoryTest(_AnthropicStubMixin):
    def setUp(self):
        super().setUp()
        self._saved_env = {}
        for key in (
            "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL",
            "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "ANTHROPIC_BASE_URL",
            "DEEPSEEK_API_KEY", "SUMMARY_API_KEY", "SUMMARY_MODEL", "DEEPSEEK_MODEL",
        ):
            import os
            self._saved_env[key] = os.environ.pop(key, None)

    def tearDown(self):
        import os
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        super().tearDown()

    def test_anthropic_key_takes_priority(self):
        import os
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        os.environ["DEEPSEEK_API_KEY"] = "sk-ds-test"
        client = create_summary_client_from_env()
        self.assertIsInstance(client, AnthropicClient)
        self.assertEqual(client.model, "claude-opus-4-8")

    def test_llm_model_env_selects_anthropic_provider(self):
        import os
        os.environ["LLM_MODEL"] = "anthropic/claude-opus-4-8"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        client = create_summary_client_from_env()
        self.assertIsInstance(client, AnthropicClient)
        self.assertEqual(client.model, "claude-opus-4-8")

    def test_deepseek_fallback_keeps_existing_behavior(self):
        import os
        os.environ["DEEPSEEK_API_KEY"] = "sk-ds-test"
        client = create_summary_client_from_env(deepseek_model="deepseek-v4-flash")
        self.assertIsInstance(client, DeepSeekClient)
        self.assertEqual(client.model, "deepseek-v4-flash")

    def test_returns_none_without_any_key(self):
        client = create_summary_client_from_env()
        self.assertIsNone(client)


class _EnvIsolationMixin(unittest.TestCase):
    _ENV_KEYS = (
        "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL",
        "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_MODEL", "DPR_USE_CLAUDE_CODE",
        "DEEPSEEK_API_KEY", "SUMMARY_API_KEY", "SUMMARY_MODEL", "DEEPSEEK_MODEL",
    )

    def setUp(self):
        import os
        self._saved_env = {key: os.environ.pop(key, None) for key in self._ENV_KEYS}

    def tearDown(self):
        import os
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class ClaudeCodeChatTest(unittest.TestCase):
    def _fake_proc(self, payload):
        import json as _json
        return SimpleNamespace(returncode=0, stdout=_json.dumps(payload), stderr="")

    def test_chat_parses_headless_json_output(self):
        import subprocess
        payload = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": '{"rewrite": "Find research papers describing x"}',
            "usage": {"input_tokens": 12, "output_tokens": 8, "cache_read_input_tokens": 3},
        }
        client = ClaudeCodeClient(oauth_token="sk-ant-oat01-test", model="opus")
        with unittest.mock.patch.object(subprocess, "run", return_value=self._fake_proc(payload)) as mock_run:
            result = client.chat([
                {"role": "system", "content": "output json"},
                {"role": "user", "content": "rewrite this"},
            ])

        self.assertEqual(result["content"], '{"rewrite": "Find research papers describing x"}')
        self.assertEqual(result["finish_reason"], "stop")
        self.assertEqual(result["tokens"]["prompt"], 15)
        self.assertEqual(result["tokens"]["content"], 8)

        args, kwargs = mock_run.call_args
        cmd = args[0]
        self.assertIn("-p", cmd)
        self.assertIn("--output-format", cmd)
        self.assertIn("json", cmd)
        self.assertIn("--model", cmd)
        self.assertIn("opus", cmd)
        self.assertIn("--system-prompt", cmd)
        self.assertEqual(kwargs["input"], "rewrite this")
        self.assertEqual(kwargs["env"]["CLAUDE_CODE_OAUTH_TOKEN"], "sk-ant-oat01-test")

    def test_chat_raises_on_cli_error(self):
        import subprocess
        proc = SimpleNamespace(returncode=1, stdout="", stderr="Invalid API key")
        client = ClaudeCodeClient(oauth_token="sk-ant-oat01-test")
        with unittest.mock.patch.object(subprocess, "run", return_value=proc):
            with self.assertRaises(RuntimeError):
                client.chat([{"role": "user", "content": "hi"}])

    def test_structured_always_uses_prompt_only(self):
        import subprocess
        payload = {
            "subtype": "success",
            "is_error": False,
            "result": '{"related": ["a"]}',
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        client = ClaudeCodeClient(oauth_token="sk-ant-oat01-test")
        schema = {
            "type": "object",
            "properties": {"related": {"type": "array", "items": {"type": "string"}}},
        }
        with unittest.mock.patch.object(subprocess, "run", return_value=self._fake_proc(payload)):
            result = client.chat_structured(
                [{"role": "user", "content": "related terms"}],
                schema_name="related",
                schema=schema,
            )
        self.assertEqual(result["response_format_used"], "prompt_only")
        self.assertEqual(result["parsed"], {"related": ["a"]})


class ClaudeCodeFactoryTest(_EnvIsolationMixin):
    def test_oauth_token_takes_priority_over_api_keys(self):
        import os
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "sk-ant-oat01-test"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        os.environ["DEEPSEEK_API_KEY"] = "sk-ds-test"
        client = create_summary_client_from_env()
        self.assertIsInstance(client, ClaudeCodeClient)

    def test_dpr_use_claude_code_flag_without_token(self):
        import os
        os.environ["DPR_USE_CLAUDE_CODE"] = "1"
        client = create_summary_client_from_env()
        self.assertIsInstance(client, ClaudeCodeClient)
        self.assertEqual(client.api_key, "")

    def test_llm_model_env_selects_claude_code_provider(self):
        import os
        os.environ["LLM_MODEL"] = "claude-code/opus"
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "sk-ant-oat01-test"
        client = create_summary_client_from_env()
        self.assertIsInstance(client, ClaudeCodeClient)
        self.assertEqual(client.model, "opus")


class SecretCleaningTest(unittest.TestCase):
    def test_pasted_whitespace_is_stripped_from_tokens(self):
        # 模拟从网页复制粘贴带入换行/空格的 token
        dirty = "sk-ant-oat01-abc\n def-ghi "
        client = ClaudeCodeClient(oauth_token=dirty)
        self.assertEqual(client.api_key, "sk-ant-oat01-abcdef-ghi")

        api_client = AnthropicClient(api_key="sk-ant-\nxyz ")
        self.assertEqual(api_client.api_key, "sk-ant-xyz")

    def test_env_token_cleaned_before_subprocess(self):
        import os
        import subprocess
        payload = {
            "subtype": "success",
            "is_error": False,
            "result": "ok",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        proc = SimpleNamespace(returncode=0, stdout=__import__("json").dumps(payload), stderr="")
        client = ClaudeCodeClient()  # 不显式传 token，走进程环境变量
        saved = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "sk-ant-oat01-abc\ndef"
        try:
            with unittest.mock.patch.object(subprocess, "run", return_value=proc) as mock_run:
                client.chat([{"role": "user", "content": "hi"}])
            env = mock_run.call_args.kwargs["env"]
            self.assertEqual(env["CLAUDE_CODE_OAUTH_TOKEN"], "sk-ant-oat01-abcdef")
        finally:
            if saved is None:
                os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
            else:
                os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = saved


class TokensIsolationTest(unittest.TestCase):
    def test_token_stats_are_instance_level(self):
        a = LLMClient(api_key="k", model="m", base_url="https://example.com")
        b = LLMClient(api_key="k", model="m", base_url="https://example.com")
        a.tokens["prompt"] += 7
        self.assertEqual(b.tokens["prompt"], 0)


if __name__ == "__main__":
    unittest.main()
