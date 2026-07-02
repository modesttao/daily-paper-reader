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


class TokensIsolationTest(unittest.TestCase):
    def test_token_stats_are_instance_level(self):
        a = LLMClient(api_key="k", model="m", base_url="https://example.com")
        b = LLMClient(api_key="k", model="m", base_url="https://example.com")
        a.tokens["prompt"] += 7
        self.assertEqual(b.tokens["prompt"], 0)


if __name__ == "__main__":
    unittest.main()
