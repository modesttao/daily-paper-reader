import json
import os
import re
import time
from typing import List, Dict, Tuple, Any, Optional

import requests

"""
统一的 LLM 客户端封装。

提供商/模型命名规则：'provider/model'，provider 大小写不敏感，model 保留大小写与路径。
当前运行链路支持 DeepSeek 与 Anthropic (Claude)；本地 reranker 不走 LLM API。
"""

# 单次实验级别的全局 token 统计（需由调用方在实验开始前手动 reset）
DEFAULT_MAX_OUTPUT_TOKENS = 393216


def resolve_max_output_tokens(default: int = DEFAULT_MAX_OUTPUT_TOKENS) -> int:
    raw = os.getenv("DPR_LLM_MAX_OUTPUT_TOKENS") or os.getenv("LLM_MAX_OUTPUT_TOKENS")
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except Exception:
        return default


GLOBAL_TOKENS = {
    'prompt': 0,    # 提示词（prompt）部分 token
    'thinking': 0,  # 推理/思维链部分 token（reasoning_tokens）
    'content': 0,   # 可见输出部分 token（completion_tokens - reasoning_tokens）
    'total': 0,     # provider 返回的总 token（通常含 prompt + completion）
}
# 单次实验级别的全局时间统计（秒）
GLOBAL_TIME_SECONDS: float = 0.0

def clean_secret(value: Any) -> str:
    """清理 API Key / OAuth token：去掉复制粘贴带入的换行、空格等空白字符。

    合法的 key/token 不含空白字符；网页复制常把换行带进 GitHub Secrets，
    导致 401 Invalid bearer token 这类难排查的鉴权失败。
    """
    return re.sub(r"\s+", "", str(value or ""))


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-8"
# Claude 输出上限（流式最高 128K，这里取安全值，避免超长请求超时）
ANTHROPIC_MAX_OUTPUT_TOKENS = 64000


def reset_global_tokens():
    """重置本次实验的全局 token 统计。"""
    GLOBAL_TOKENS['prompt'] = 0
    GLOBAL_TOKENS['thinking'] = 0
    GLOBAL_TOKENS['content'] = 0
    GLOBAL_TOKENS['total'] = 0


def get_global_tokens() -> Dict[str, int]:
    """获取本次实验的全局 token 统计（thinking/content/total）。"""
    return dict(GLOBAL_TOKENS)


def reset_global_time():
    """重置本次实验的大模型总耗时统计（秒）。"""
    global GLOBAL_TIME_SECONDS
    GLOBAL_TIME_SECONDS = 0.0


def get_global_time() -> float:
    """获取本次实验的大模型总耗时（秒）。"""
    return float(GLOBAL_TIME_SECONDS)


class LLMClient:

    def __init__(self, api_key: str, model: str, base_url: str):
        """
        初始化 LLM 客户端。

        :param api_key: API 密钥
        :param model: 模型名称
        :param base_url: API 的基础 URL
        """
        self.api_key = clean_secret(api_key)
        self.model = model
        self.base_url = base_url
        # 实例级 token 统计（不能放在类属性上，否则所有 client 共享同一个 dict）
        self.tokens = {
            'prompt': 0,
            'content': 0,
            'reasoning': 0,
            'total': 0,
        }
        self._base_urls = self._normalize_base_urls([base_url])
        # 实例级别的累计统计（无需显式 reset；通常每个实验构造一个 client）
        self._call_index = 0
        self._cum_tokens = {
            'prompt': 0,
            'thinking': 0,
            'content': 0,
            'total': 0,
        }
        # 实例级别的累计耗时（秒）
        self._cum_time_seconds: float = 0.0
        self.kwargs: Dict[str, Any] = {
            'max_tokens': resolve_max_output_tokens(),
            'temperature': 0.6,
            'top_p': 0.3,
            'top_k': 50,
            'frequency_penalty': 0.5,
            'n': 1,
            'stream': False,
        }

    @staticmethod
    def _normalize_base_urls(urls: List[str | None]) -> List[str]:
        out: List[str] = []
        for url in urls:
            if not url:
                continue
            candidate = str(url).strip().rstrip("/")
            if candidate and candidate not in out:
                out.append(candidate)
        return out

    def _iter_request_bases(self) -> List[str]:
        return self._normalize_base_urls(self._base_urls)

    @staticmethod
    def _build_chat_completions_url(base_url: str | None) -> str:
        raw = str(base_url or "").strip().rstrip("/")
        if not raw:
            raise ValueError("缺少可用的 LLM base_url")
        if raw.lower().endswith("/chat/completions"):
            return raw
        if re.search(r"/v\d+$", raw, re.IGNORECASE):
            return f"{raw}/chat/completions"
        return f"{raw}/v1/chat/completions"

    def _iter_retry_bases(self, total_attempts: int = 6) -> List[str]:
        bases = self._iter_request_bases()
        if total_attempts <= 0:
            return []
        if not bases:
            return []

        if len(bases) == 1:
            return [bases[0]] * total_attempts

        attempts: List[str] = []
        for idx in range(total_attempts):
            attempts.append(bases[idx % len(bases)])
        return attempts

    def _provider_name(self, base_url: str | None = None) -> str:
        try:
            url = (base_url or self.base_url or '').lower()
            model = str(self.model or '').strip().lower()
            if 'deepseek' in url:
                return 'deepseek'
            if model.startswith('deepseek-'):
                return 'deepseek'
        except Exception:
            pass
        return 'llm'

    @staticmethod
    def _is_authentication_error(exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code in (401, 403):
            return True
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code in (401, 403):
            return True
        message = str(exc or "").lower()
        return any(token in message for token in (
            "authentication fails",
            "invalid api key",
            "invalid x-api-key",
            "authorization required",
            "unauthorized",
        ))

    def _record_call_stats(
        self,
        *,
        prompt_tokens: int,
        reasoning_tokens: int,
        visible_tokens: int,
        total_tokens: int,
        elapsed: float,
    ) -> None:
        """统一记录单次调用的 token / 耗时统计（实例级 + 全局）。"""
        self.tokens['prompt'] += prompt_tokens
        self.tokens['content'] += visible_tokens
        self.tokens['reasoning'] += reasoning_tokens
        self.tokens['total'] += total_tokens

        try:
            GLOBAL_TOKENS['prompt'] += int(prompt_tokens)
            GLOBAL_TOKENS['thinking'] += int(reasoning_tokens)
            GLOBAL_TOKENS['content'] += int(visible_tokens)
            GLOBAL_TOKENS['total'] += int(total_tokens)
        except Exception:
            pass

        try:
            global GLOBAL_TIME_SECONDS
            GLOBAL_TIME_SECONDS += float(elapsed)
            self._cum_time_seconds += float(elapsed)

            self._call_index += 1
            self._cum_tokens['prompt'] += int(prompt_tokens)
            self._cum_tokens['thinking'] += int(reasoning_tokens)
            self._cum_tokens['content'] += int(visible_tokens)
            self._cum_tokens['total'] += int(total_tokens)

            provider = self._provider_name()
            header = f"[{provider}][{self.model}] 第{self._call_index}次"
            line_cur = (
                f"本次 tokens：prompt={int(prompt_tokens)}, thinking={int(reasoning_tokens)}, "
                f"content={int(visible_tokens)}, total={int(total_tokens)}"
            )
            line_cum = (
                f"累计 tokens：prompt={self._cum_tokens['prompt']}, thinking={self._cum_tokens['thinking']}, "
                f"content={self._cum_tokens['content']}, total={self._cum_tokens['total']}"
            )
            line_time = (
                f"本次用时：{elapsed:.2f}s，"
                f"累计用时：{self._cum_time_seconds:.2f}s"
            )
            print(header + "\n" + line_cur + "\n" + line_cum + "\n" + line_time)
        except Exception:
            pass

    @staticmethod
    def _extract_text_content(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: List[str] = []
            for item in value:
                text = LLMClient._extract_text_content(item)
                if text:
                    parts.append(text)
            return "\n".join(parts).strip()
        if isinstance(value, dict):
            for key in ("text", "content", "value"):
                text = value.get(key)
                if isinstance(text, str) and text.strip():
                    return text
        return ""

    @staticmethod
    def _strip_json_wrappers(text: str) -> str:
        cleaned = (text or "").strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()

    @staticmethod
    def _repair_json_suffix(text: str) -> str:
        if not text:
            return text

        stack: List[str] = []
        in_str = False
        escaped = False

        for ch in text:
            if in_str:
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    in_str = False
                continue

            if ch == '"':
                in_str = True
            elif ch == '{':
                stack.append('}')
            elif ch == '[':
                stack.append(']')
            elif ch in ('}', ']'):
                if stack and stack[-1] == ch:
                    stack.pop()

        repaired = text
        if in_str:
            repaired += '"'
        if stack:
            repaired += ''.join(reversed(stack))
        repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
        return repaired

    @classmethod
    def parse_json_content(cls, text: str) -> Any:
        raw = cls._strip_json_wrappers((text or "").strip())
        if not raw:
            return None

        decoder = json.JSONDecoder()
        candidates: List[str] = []
        first_obj = raw.find("{")
        last_obj = raw.rfind("}")
        first_arr = raw.find("[")
        last_arr = raw.rfind("]")
        if first_obj != -1:
            candidates.append(raw[first_obj:])
            if last_obj != -1 and last_obj >= first_obj:
                candidates.append(raw[first_obj:last_obj + 1])
        if first_arr != -1:
            candidates.append(raw[first_arr:])
            if last_arr != -1 and last_arr >= first_arr:
                candidates.append(raw[first_arr:last_arr + 1])
        candidates.append(raw)

        seen: set[str] = set()
        last_exc: Exception | None = None
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                obj, _idx = decoder.raw_decode(candidate)
                return obj
            except Exception as exc:
                last_exc = exc
                repaired = cls._repair_json_suffix(candidate)
                if repaired == candidate:
                    continue
                try:
                    return json.loads(repaired)
                except Exception as exc2:
                    last_exc = exc2

        raise ValueError(f"模型未返回合法 JSON：{raw[:500]}") from last_exc

    @staticmethod
    def build_json_schema_response_format(
        schema_name: str,
        schema: Dict[str, Any],
        strict: bool = True,
    ) -> Dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": bool(strict),
            },
        }

    @staticmethod
    def build_json_object_response_format() -> Dict[str, str]:
        return {"type": "json_object"}

    def _structured_response_format_names(
        self,
        allow_json_object_fallback: bool,
    ) -> List[str]:
        """
        按主请求端点选择结构化输出格式。

        DeepSeek 官方 JSON Output 稳定入口是 json_object，因此默认不发送 json_schema。
        可用 DPR_LLM_STRUCTURED_FORMAT/LLM_STRUCTURED_FORMAT 覆盖：
        - json_schema: 强制 json_schema，允许时再回退 json_object
        - json_object: 强制 json_object
        - auto: 使用默认判断
        """
        if not allow_json_object_fallback:
            return ["json_schema"]

        override = (
            os.getenv("DPR_LLM_STRUCTURED_FORMAT")
            or os.getenv("LLM_STRUCTURED_FORMAT")
            or ""
        ).strip().lower().replace("-", "_")
        if override in ("prompt_only", "prompt", "none", "text"):
            return ["prompt_only"]
        if override in ("json_object", "object", "json"):
            return ["json_object", "prompt_only"]
        if override in ("json_schema", "schema", "structured"):
            return ["json_schema", "json_object", "prompt_only"]

        return ["json_object", "prompt_only"]

    @staticmethod
    def _messages_contain_json_instruction(messages: List[Dict[str, str]]) -> bool:
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str) and "json" in content.lower():
                return True
        return False

    @classmethod
    def _ensure_json_instruction(
        cls,
        messages: List[Dict[str, str]],
        format_name: str,
    ) -> List[Dict[str, str]]:
        if format_name not in ("json_object", "prompt_only"):
            return messages
        if cls._messages_contain_json_instruction(messages):
            return messages
        return [
            {
                "role": "system",
                "content": "Output valid JSON only. Do not output Markdown, code fences, or explanatory text.",
            },
            *(messages or []),
        ]

    @classmethod
    def _validate_json_schema_subset(
        cls,
        value: Any,
        schema: Dict[str, Any],
        path: str = "$",
    ) -> str | None:
        if not isinstance(schema, dict):
            return None

        expected_type = schema.get("type")
        expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
        expected_types = [item for item in expected_types if isinstance(item, str)]

        def type_matches(type_name: str) -> bool:
            if type_name == "object":
                return isinstance(value, dict)
            if type_name == "array":
                return isinstance(value, list)
            if type_name == "string":
                return isinstance(value, str)
            if type_name == "number":
                return isinstance(value, (int, float)) and not isinstance(value, bool)
            if type_name == "integer":
                return isinstance(value, int) and not isinstance(value, bool)
            if type_name == "boolean":
                return isinstance(value, bool)
            if type_name == "null":
                return value is None
            return True

        if expected_types and not any(type_matches(type_name) for type_name in expected_types):
            return f"{path}: expected type {expected_types}, got {type(value).__name__}"

        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and value not in enum_values:
            return f"{path}: value is not in enum"

        if expected_type == "object" or isinstance(value, dict):
            if not isinstance(value, dict):
                return f"{path}: expected object"
            properties = schema.get("properties")
            properties = properties if isinstance(properties, dict) else {}
            required = schema.get("required")
            required = required if isinstance(required, list) else []
            for key in required:
                if isinstance(key, str) and key not in value:
                    return f"{path}.{key}: missing required field"
            if schema.get("additionalProperties") is False:
                extra = sorted(set(value.keys()) - set(properties.keys()))
                if extra:
                    return f"{path}: unexpected fields {extra}"
            for key, child_schema in properties.items():
                if key not in value:
                    continue
                err = cls._validate_json_schema_subset(value[key], child_schema, f"{path}.{key}")
                if err:
                    return err

        if expected_type == "array" or isinstance(value, list):
            if not isinstance(value, list):
                return f"{path}: expected array"
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for idx, item in enumerate(value):
                    err = cls._validate_json_schema_subset(item, item_schema, f"{path}[{idx}]")
                    if err:
                        return err

        return None

    def _build_response_format_by_name(
        self,
        format_name: str,
        schema_name: str,
        schema: Dict[str, Any],
        strict: bool,
    ) -> Dict[str, Any] | None:
        if format_name == "json_schema":
            return self.build_json_schema_response_format(
                schema_name=schema_name,
                schema=schema,
                strict=strict,
            )
        if format_name == "json_object":
            return self.build_json_object_response_format()
        if format_name == "prompt_only":
            return None
        raise ValueError(f"未知结构化输出格式: {format_name}")

    @staticmethod
    def _is_structured_output_unsupported_error(error: Exception) -> bool:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        text = ""
        if response is not None:
            try:
                text = response.text or ""
            except Exception:
                text = ""
        if not text:
            text = str(error or "")
        lowered = text.lower()
        has_target = any(token in lowered for token in (
            "response_format",
            "json_schema",
            "json object",
            "json_object",
        ))
        has_signal = any(token in lowered for token in (
            "unsupported",
            "not support",
            "not supported",
            "invalid",
            "unknown",
            "unrecognized",
            "extra inputs",
            "unexpected",
            "must be one of",
            "one of",
            "allowed values",
            "enum",
        ))
        if has_target and has_signal:
            return True
        if (
            status_code in (400, 404, 415, 422)
            and "response_format" in lowered
            and any(token in lowered for token in ("json_object", "json_schema", "text"))
        ):
            return True
        if status_code in (400, 404, 415, 422) and "response_format" in lowered:
            return True
        return False

    def chat(self, messages: List[Dict[str, str]], response_format: Optional[Dict[str, Any]] = None) -> dict:
        """
        统一 Chat Completions 请求。

        :param messages: OpenAI 格式的消息列表
        :param response_format: 可选，结构化输出配置（DeepSeek JSON mode）
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        model_name = self.model
        if 'qwen3' in model_name.lower():
            if '/think' in model_name:
                self.kwargs['enable_thinking'] = True
                model_name = model_name.replace('/think', '')
            else:
                self.kwargs['enable_thinking'] = False
                model_name = model_name.replace('/think', '')

        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
        }
        # 仅透传 OpenAI Chat Completions 兼容字段，避免提供商拒绝未知参数
        allowed_keys = {
            'max_tokens', 'temperature', 'top_p', 'n', 'stream',
            'presence_penalty', 'frequency_penalty', 'stop', 'logprobs',
            'tools', 'tool_choice', 'logit_bias',
            'response_format',
        }
        if isinstance(self.kwargs, dict):
            for k, v in self.kwargs.items():
                if k in allowed_keys:
                    payload[k] = v
        if response_format is not None:
            payload['response_format'] = response_format

        # 对输出 token 上限做保护；DeepSeek V4 支持更长输出，默认按 384K 预留。
        try:
            max_output_tokens = resolve_max_output_tokens()
            if isinstance(payload.get('max_tokens'), int) and payload['max_tokens'] > max_output_tokens:
                payload['max_tokens'] = max_output_tokens
        except Exception:
            pass

        start_time = time.time()
        request_bases = self._iter_retry_bases(total_attempts=6)
        last_error: Exception | None = None
        for attempt_idx, req_base in enumerate(request_bases, start=1):
            request_url = self._build_chat_completions_url(req_base)
            try:
                response = requests.post(request_url, headers=headers, json=payload, timeout=120)
                response.raise_for_status()
                try:
                    response_data = response.json()
                except ValueError:
                    print("API 响应无法解析为 JSON，原始文本预览:", response.text[:500])
                    raise

                debug_raw = os.getenv("LLM_DEBUG_RAW") == "1"
                if debug_raw:
                    print("[DEBUG] LLM 原始响应包:", response.text)

                if isinstance(response_data, dict) and 'error' in response_data:
                    err = response_data.get('error') or {}
                    print("API 返回错误:", {
                        'type': err.get('type'),
                        'code': err.get('code'),
                        'message': err.get('message') or err,
                    })
                    raise requests.exceptions.HTTPError(f"API error: {err}")

                if 'choices' not in response_data or not response_data['choices']:
                    print("API 响应不包含 choices 字段或为空：", str(response_data)[:500])
                    raise requests.exceptions.HTTPError("API response missing choices")

                choice = response_data['choices'][0] if isinstance(response_data['choices'][0], dict) else {}
                message = choice.get('message', {}) if isinstance(choice, dict) else {}
                content = self._extract_text_content(message.get('content'))
                reasoning_content = self._extract_text_content(message.get('reasoning_content'))
                refusal = str(message.get('refusal') or '').strip()
                finish_reason = choice.get('finish_reason') if isinstance(choice, dict) else None

                usage = response_data.get('usage', {})
                prompt_tokens = usage.get('prompt_tokens', 0)
                completion_tokens = usage.get('completion_tokens', 0)
                total_tokens = usage.get('total_tokens', 0)
                reasoning_tokens = 0
                if 'completion_tokens_details' in usage:
                    reasoning_tokens = usage['completion_tokens_details'].get('reasoning_tokens', 0)

                self.tokens['prompt'] += prompt_tokens
                self.tokens['content'] += completion_tokens - reasoning_tokens
                self.tokens['reasoning'] += reasoning_tokens
                self.tokens['total'] += total_tokens

                try:
                    GLOBAL_TOKENS['prompt'] += int(prompt_tokens)
                    GLOBAL_TOKENS['thinking'] += int(reasoning_tokens)
                    GLOBAL_TOKENS['content'] += int(completion_tokens - reasoning_tokens)
                    GLOBAL_TOKENS['total'] += int(total_tokens)
                except Exception:
                    pass

                try:
                    elapsed = time.time() - start_time
                    self._cum_time_seconds += float(elapsed)
                    try:
                        global GLOBAL_TIME_SECONDS
                        GLOBAL_TIME_SECONDS += float(elapsed)
                    except Exception:
                        pass

                    self._call_index += 1
                    self._cum_tokens['prompt'] += int(prompt_tokens)
                    self._cum_tokens['thinking'] += int(reasoning_tokens)
                    self._cum_tokens['content'] += int(completion_tokens - reasoning_tokens)
                    self._cum_tokens['total'] += int(total_tokens)

                    provider = self._provider_name(req_base)
                    header = f"[{provider}][{self.model}] 第{self._call_index}次"
                    line_cur = (
                        f"本次 tokens：prompt={int(prompt_tokens)}, thinking={int(reasoning_tokens)}, "
                        f"content={int(completion_tokens - reasoning_tokens)}, total={int(total_tokens)}"
                    )
                    line_cum = (
                        f"累计 tokens：prompt={self._cum_tokens['prompt']}, thinking={self._cum_tokens['thinking']}, "
                        f"content={self._cum_tokens['content']}, total={self._cum_tokens['total']}"
                    )
                    line_time = (
                        f"本次用时：{elapsed:.2f}s，"
                        f"累计用时：{self._cum_time_seconds:.2f}s"
                    )
                    print(header + "\n" + line_cur + "\n" + line_cum + "\n" + line_time)
                except Exception:
                    pass

                return {
                    "content": content,
                    "raw_content": message.get('content'),
                    "reasoning_content": reasoning_content,
                    "refusal": refusal,
                    "finish_reason": finish_reason,
                    "message": message,
                    "raw_response": response_data,
                    "tokens": {
                        "prompt": prompt_tokens,
                        "content": completion_tokens - reasoning_tokens,
                        "reasoning": reasoning_tokens,
                        "total": total_tokens
                    }
                }

            except Exception as e:
                last_error = e
                if self._is_authentication_error(e):
                    print(
                        "LLM 鉴权失败：当前 API Key 无效或无权限，请在本地配置中更新 DeepSeek API Key 后重试。"
                    )
                    if hasattr(e, "response") and e.response is not None:
                        try:
                            print("错误详情(JSON):", e.response.json())
                        except ValueError:
                            try:
                                print("错误详情(TEXT):", e.response.text[:500])
                            except Exception:
                                pass
                    raise
                if response_format is not None and self._is_structured_output_unsupported_error(e):
                    raise
                if attempt_idx < len(request_bases):
                    next_base = request_bases[attempt_idx] if attempt_idx < len(request_bases) else ''
                    print(
                        f"请求失败（base={req_base}，第 {attempt_idx} 次），"
                        f"将回退到 {next_base}"
                    )
                    if hasattr(e, "response") and e.response is not None:
                        try:
                            print("错误详情(JSON):", e.response.json())
                        except ValueError:
                            try:
                                print("错误详情(TEXT):", e.response.text[:500])
                            except Exception:
                                pass
                    continue
                print(f"通过 requests 调用 API 时出错: {e}")
                if hasattr(e, "response") and e.response is not None:
                    try:
                        print("错误详情(JSON):", e.response.json())
                    except ValueError:
                        try:
                            print("错误详情(TEXT):", e.response.text[:500])
                        except Exception:
                            pass
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("LLM 请求未命中可用 base")

    def chat_structured(
        self,
        messages: List[Dict[str, str]],
        schema_name: str,
        schema: Dict[str, Any],
        *,
        strict: bool = True,
        allow_json_object_fallback: bool = True,
    ) -> Dict[str, Any]:
        attempts: List[Tuple[str, Dict[str, Any] | None]] = [
            (
                format_name,
                self._build_response_format_by_name(
                    format_name=format_name,
                    schema_name=schema_name,
                    schema=schema,
                    strict=strict,
                ),
            )
            for format_name in self._structured_response_format_names(
                allow_json_object_fallback=allow_json_object_fallback,
            )
        ]

        last_error: Exception | None = None
        for idx, (format_name, response_format) in enumerate(attempts):
            try:
                request_messages = self._ensure_json_instruction(messages, format_name)
                response = self.chat(messages=request_messages, response_format=response_format)
            except Exception as exc:
                last_error = exc
                if (
                    idx + 1 < len(attempts)
                    and response_format is not None
                    and self._is_structured_output_unsupported_error(exc)
                ):
                    print(
                        f"[INFO] Structured Outputs 不受支持，回退到 {attempts[idx + 1][0]}。"
                    )
                    continue
                raise

            parsed = None
            parse_error: Exception | None = None
            if not response.get("refusal"):
                content = str(response.get("content") or "").strip()
                if content:
                    try:
                        parsed = self.parse_json_content(content)
                    except Exception as exc:
                        parse_error = exc
                    if parsed is not None and parse_error is None:
                        schema_error = self._validate_json_schema_subset(parsed, schema)
                        if schema_error:
                            parse_error = ValueError(f"JSON schema validation failed: {schema_error}")

            if parse_error is not None and idx + 1 < len(attempts):
                print(
                    f"[INFO] {format_name} 返回内容未通过 JSON 校验，"
                    f"回退到 {attempts[idx + 1][0]}。"
                )
                continue

            structured = dict(response)
            structured["parsed"] = parsed
            structured["parse_error"] = parse_error
            structured["response_format_used"] = format_name
            return structured

        if last_error is not None:
            raise last_error
        raise RuntimeError("结构化输出请求未命中可用格式")

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
        model: Optional[str] = None,
    ) -> dict:
        """重排序接口不走远端 LLM API，请使用本地 reranker。"""
        raise NotImplementedError("远端 rerank 已关闭，请使用 src/3.rank_papers.py 的本地 reranker。")


class DeepSeekClient(LLMClient):
    def __init__(self, api_key: str, model: str, base_url: str = DEFAULT_DEEPSEEK_BASE_URL):
        super().__init__(api_key=api_key, model=model, base_url=base_url)


class AnthropicClient(LLMClient):
    """Claude 客户端：走官方 anthropic SDK 的 Messages API。

    与 OpenAI Chat Completions 的差异在这里统一适配：
    - system 消息提升为顶层 system 参数；
    - 不透传采样参数（Claude 4.7+ 拒绝 temperature/top_p/top_k）；
    - response_format(json_schema) 映射为 output_config.format；
    - usage 字段从 input_tokens/output_tokens 映射回统一结构。
    """

    _UNSUPPORTED_SCHEMA_KEYS = frozenset({
        "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
        "minLength", "maxLength", "pattern",
        "minItems", "maxItems", "uniqueItems",
        "default",
    })

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_ANTHROPIC_MODEL,
        base_url: str | None = None,
    ):
        super().__init__(api_key=api_key, model=model, base_url=base_url or "")
        self._sdk_client = None

    def _get_sdk_client(self):
        if self._sdk_client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "使用 Claude API 需要安装官方 SDK：pip install anthropic"
                ) from exc
            client_kwargs: Dict[str, Any] = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            self._sdk_client = anthropic.Anthropic(**client_kwargs)
        return self._sdk_client

    def _provider_name(self, base_url: str | None = None) -> str:
        return 'anthropic'

    def _structured_response_format_names(
        self,
        allow_json_object_fallback: bool,
    ) -> List[str]:
        # Claude 没有 json_object 模式：优先原生 json_schema（output_config.format），
        # 不支持或校验失败时回退到提示词约束 + 本地 JSON 解析修复。
        if not allow_json_object_fallback:
            return ["json_schema"]
        override = (
            os.getenv("DPR_LLM_STRUCTURED_FORMAT")
            or os.getenv("LLM_STRUCTURED_FORMAT")
            or ""
        ).strip().lower().replace("-", "_")
        if override in ("prompt_only", "prompt", "none", "text"):
            return ["prompt_only"]
        return ["json_schema", "prompt_only"]

    @staticmethod
    def _is_structured_output_unsupported_error(error: Exception) -> bool:
        status_code = getattr(error, "status_code", None)
        lowered = str(error or "").lower()
        if status_code == 400 and any(token in lowered for token in (
            "output_config", "format", "schema", "structured",
        )):
            return True
        return LLMClient._is_structured_output_unsupported_error(error)

    @classmethod
    def _prepare_output_schema(cls, schema: Any) -> Any:
        """把项目内的宽松 JSON Schema 收敛为 Claude 结构化输出可接受的子集。

        Claude 要求 object 节点带 additionalProperties: false，且不支持
        数值/字符串/数组约束关键字（超出会 400）。
        """
        if not isinstance(schema, dict):
            return schema
        out: Dict[str, Any] = {}
        for key, value in schema.items():
            if key in cls._UNSUPPORTED_SCHEMA_KEYS:
                continue
            if key in ("properties", "$defs", "definitions") and isinstance(value, dict):
                out[key] = {name: cls._prepare_output_schema(child) for name, child in value.items()}
            elif key == "items":
                out[key] = cls._prepare_output_schema(value)
            elif key in ("anyOf", "allOf", "oneOf") and isinstance(value, list):
                out[key] = [cls._prepare_output_schema(item) for item in value]
            else:
                out[key] = value
        if out.get("type") == "object" and isinstance(out.get("properties"), dict):
            out.setdefault("additionalProperties", False)
            out.setdefault("required", list(out["properties"].keys()))
        return out

    def chat(self, messages: List[Dict[str, str]], response_format: Optional[Dict[str, Any]] = None) -> dict:
        system_parts: List[str] = []
        turns: List[Dict[str, Any]] = []
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "").strip().lower()
            content = self._extract_text_content(message.get("content"))
            if role == "system":
                if content:
                    system_parts.append(content)
            elif role in ("user", "assistant") and content:
                turns.append({"role": role, "content": content})
        if not turns:
            turns = [{"role": "user", "content": "请根据系统提示完成任务。"}]

        max_tokens = ANTHROPIC_MAX_OUTPUT_TOKENS
        try:
            configured = int(self.kwargs.get("max_tokens") or 0)
            if configured > 0:
                max_tokens = min(configured, ANTHROPIC_MAX_OUTPUT_TOKENS)
        except Exception:
            pass

        params: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": turns,
        }
        if system_parts:
            params["system"] = "\n\n".join(system_parts)
        if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
            schema = (response_format.get("json_schema") or {}).get("schema") or {}
            params["output_config"] = {
                "format": {
                    "type": "json_schema",
                    "schema": self._prepare_output_schema(schema),
                }
            }

        sdk = self._get_sdk_client()
        start_time = time.time()
        try:
            # 统一走流式再取完整消息，避免大 max_tokens 触发 SDK 的非流式超时保护
            with sdk.messages.stream(**params) as stream:
                response_message = stream.get_final_message()
        except Exception as exc:
            if self._is_authentication_error(exc):
                print("LLM 鉴权失败：ANTHROPIC_API_KEY 无效或无权限，请更新后重试。")
            raise

        content_parts: List[str] = []
        for block in getattr(response_message, "content", None) or []:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", "") or ""
                if text:
                    content_parts.append(text)
        content = "".join(content_parts).strip()

        stop_reason = getattr(response_message, "stop_reason", None)
        refusal = ""
        if stop_reason == "refusal":
            refusal = "Claude 拒绝了本次请求（stop_reason=refusal）。"
        # 归一化为 OpenAI 语义，调用方按 None/"stop"/"length" 判断
        finish_reason = {
            "end_turn": "stop",
            "stop_sequence": "stop",
            "max_tokens": "length",
        }.get(stop_reason, stop_reason)

        usage = getattr(response_message, "usage", None)
        prompt_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        total_tokens = prompt_tokens + completion_tokens

        self._record_call_stats(
            prompt_tokens=prompt_tokens,
            reasoning_tokens=0,
            visible_tokens=completion_tokens,
            total_tokens=total_tokens,
            elapsed=time.time() - start_time,
        )

        return {
            "content": content,
            "raw_content": content,
            "reasoning_content": "",
            "refusal": refusal,
            "finish_reason": finish_reason,
            "message": {"role": "assistant", "content": content},
            "raw_response": response_message,
            "tokens": {
                "prompt": prompt_tokens,
                "content": completion_tokens,
                "reasoning": 0,
                "total": total_tokens,
            },
        }


class ClaudeCodeClient(LLMClient):
    """通过本地 Claude Code CLI（`claude -p`）调用 Claude，消耗 Pro/Max 订阅额度。

    与直连 API 的差异：
    - 鉴权走 CLAUDE_CODE_OAUTH_TOKEN（`claude setup-token` 生成）或本机已登录的 Claude Code；
    - 不支持 max_tokens / 采样参数 / json_schema 结构化输出，
      结构化输出统一回退到提示词约束 + 本地 JSON 解析修复；
    - 订阅额度有 5 小时滚动窗口与 7 天滚动上限，批量调用会与交互使用共享额度。
    """

    DEFAULT_TIMEOUT_SECONDS = 600
    # 防跑飞的轮数上限：设 1 会让模型偶发的内部工具调用直接报 error_max_turns，
    # 线上观测 num_turns 通常为 1-2，这里留足余量。
    DEFAULT_MAX_TURNS = 5
    NO_TOOLS_INSTRUCTION = (
        "Answer directly in a single message. Do not use any tools, "
        "do not read or write files, and do not run commands."
    )

    def __init__(
        self,
        oauth_token: str = '',
        model: str = '',
        cli_path: str | None = None,
    ):
        cli_model = str(model or '').strip()
        super().__init__(
            api_key=oauth_token,
            model=cli_model or 'subscription-default',
            base_url='',
        )
        self._cli_model = cli_model
        self.cli_path = (
            cli_path
            or (os.getenv('CLAUDE_CODE_CLI_PATH') or '').strip()
            or 'claude'
        )

    def _provider_name(self, base_url: str | None = None) -> str:
        return 'claude-code'

    def _structured_response_format_names(
        self,
        allow_json_object_fallback: bool,
    ) -> List[str]:
        # Claude Code headless 只输出文本，结构化输出永远走提示词约束。
        return ["prompt_only"]

    @staticmethod
    def _resolve_timeout_seconds() -> int:
        raw = (os.getenv('CLAUDE_CODE_TIMEOUT_SECONDS') or '').strip()
        try:
            value = int(raw)
            if value > 0:
                return value
        except Exception:
            pass
        return ClaudeCodeClient.DEFAULT_TIMEOUT_SECONDS

    @staticmethod
    def _resolve_max_turns() -> int:
        raw = (os.getenv('CLAUDE_CODE_MAX_TURNS') or '').strip()
        try:
            value = int(raw)
            if value > 0:
                return value
        except Exception:
            pass
        return ClaudeCodeClient.DEFAULT_MAX_TURNS

    def chat(self, messages: List[Dict[str, str]], response_format: Optional[Dict[str, Any]] = None) -> dict:
        import subprocess
        import tempfile

        system_parts: List[str] = []
        prompt_parts: List[str] = []
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "").strip().lower()
            content = self._extract_text_content(message.get("content"))
            if not content:
                continue
            if role == "system":
                system_parts.append(content)
            elif role == "assistant":
                prompt_parts.append(f"[之前的助手回复]\n{content}")
            else:
                prompt_parts.append(content)
        prompt = "\n\n".join(prompt_parts).strip() or "请根据系统提示完成任务。"

        cmd = [
            self.cli_path, '-p',
            '--output-format', 'json',
            '--max-turns', str(self._resolve_max_turns()),
        ]
        if self._cli_model:
            cmd += ['--model', self._cli_model]
        cmd += ['--system-prompt', "\n\n".join([*system_parts, self.NO_TOOLS_INSTRUCTION])]

        env = os.environ.copy()
        if self.api_key:
            env['CLAUDE_CODE_OAUTH_TOKEN'] = self.api_key
        else:
            # 未显式传 token 时也清理进程环境里的值，避免粘贴带入的空白字符导致 401
            env_token = clean_secret(env.get('CLAUDE_CODE_OAUTH_TOKEN'))
            if env_token:
                env['CLAUDE_CODE_OAUTH_TOKEN'] = env_token

        start_time = time.time()
        try:
            # 在临时目录里执行，避免 Claude Code 读取当前仓库上下文
            with tempfile.TemporaryDirectory() as workdir:
                proc = subprocess.run(
                    cmd,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    env=env,
                    cwd=workdir,
                    timeout=self._resolve_timeout_seconds(),
                )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"找不到 Claude Code CLI（{self.cli_path}）。"
                "请先安装：npm install -g @anthropic-ai/claude-code"
            ) from exc

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or '').strip()[:500]
            lowered = detail.lower()
            if any(token in lowered for token in ("invalid api key", "unauthorized", "authentication", "oauth")):
                print("LLM 鉴权失败：CLAUDE_CODE_OAUTH_TOKEN 无效或已过期，请重新执行 claude setup-token。")
            raise RuntimeError(f"claude -p 调用失败 (exit={proc.returncode}): {detail}")

        try:
            data = json.loads((proc.stdout or '').strip() or '{}')
        except ValueError as exc:
            raise RuntimeError(f"claude -p 输出无法解析为 JSON：{(proc.stdout or '')[:500]}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"claude -p 输出结构异常：{str(data)[:500]}")
        if data.get('is_error'):
            raise RuntimeError(f"claude -p 返回错误：{str(data)[:500]}")

        content = str(data.get('result') or '').strip()
        usage = data.get('usage') or {}
        prompt_tokens = (
            int(usage.get('input_tokens') or 0)
            + int(usage.get('cache_read_input_tokens') or 0)
            + int(usage.get('cache_creation_input_tokens') or 0)
        )
        completion_tokens = int(usage.get('output_tokens') or 0)
        total_tokens = prompt_tokens + completion_tokens

        self._record_call_stats(
            prompt_tokens=prompt_tokens,
            reasoning_tokens=0,
            visible_tokens=completion_tokens,
            total_tokens=total_tokens,
            elapsed=time.time() - start_time,
        )

        return {
            "content": content,
            "raw_content": content,
            "reasoning_content": "",
            "refusal": "",
            # 归一化为 OpenAI 语义：success -> stop，其余保留原值便于排查
            "finish_reason": "stop" if data.get('subtype') == 'success' else data.get('subtype'),
            "message": {"role": "assistant", "content": content},
            "raw_response": data,
            "tokens": {
                "prompt": prompt_tokens,
                "content": completion_tokens,
                "reasoning": 0,
                "total": total_tokens,
            },
        }


def parse_provider_model(model_str: str) -> Tuple[str, str]:
    """
    解析模型字符串为 (provider, model)。

    规则：第一个 '/' 之前为提供商（大小写不敏感），之后的全部为模型名（大小写敏感，允许包含 '/').
    示例：
    - "deepseek/deepseek-v4-flash" -> ("deepseek", "deepseek-v4-flash")
    - "anthropic/claude-opus-4-8" -> ("anthropic", "claude-opus-4-8")
    """
    if not isinstance(model_str, str) or '/' not in model_str:
        raise ValueError(
            "缺少模型提供商：请使用 'provider/model' 格式，"
            "例如 'deepseek/deepseek-v4-flash' 或 'anthropic/claude-opus-4-8'"
        )
    provider, model = model_str.split('/', 1)
    return provider.lower(), model


class ClientFactory:
    @staticmethod
    def from_env():
        """
        基于环境变量创建具体客户端。

        必填：
        - LLM_MODEL：形如 'provider/model'。
        选填：
        - LLM_API_KEY：通用 API key（优先级高于各 provider 专用 key）
        - LLM_BASE_URL：通用 base_url（优先级高于默认 base_url）
        """
        model_env = (os.getenv('LLM_MODEL') or '').strip()
        if not model_env:
            raise ValueError("缺少必要环境变量: LLM_MODEL（格式为 'deepseek/model'）")

        provider, model = parse_provider_model(model_env)
        api_key = (os.getenv('LLM_API_KEY') or '').strip() or None
        base_url = (os.getenv('LLM_BASE_URL') or '').strip() or None

        if provider == 'deepseek':
            base_url = base_url or DEFAULT_DEEPSEEK_BASE_URL
            return DeepSeekClient(api_key=api_key or os.getenv('DEEPSEEK_API_KEY', ''), model=model, base_url=base_url)
        if provider in ('anthropic', 'claude'):
            key = api_key or (os.getenv('ANTHROPIC_API_KEY') or '').strip()
            base_url = base_url or (os.getenv('ANTHROPIC_BASE_URL') or '').strip() or None
            return AnthropicClient(api_key=key, model=model, base_url=base_url)
        if provider in ('claude-code', 'claude_code', 'claudecode'):
            token = api_key or (os.getenv('CLAUDE_CODE_OAUTH_TOKEN') or '').strip()
            cli_model = '' if model.strip().lower() in ('default', 'subscription') else model
            return ClaudeCodeClient(oauth_token=token, model=cli_model)
        raise ValueError(
            f"当前支持 DeepSeek / Anthropic / Claude Code，请使用 'deepseek/模型名'、"
            f"'anthropic/模型名' 或 'claude-code/模型名'，当前 provider={provider}"
        )

    @staticmethod
    def from_config(_config: dict | None = None):
        """
        兼容旧调用入口，但不再读取 config 文件，统一从环境变量读取。
        """
        return ClientFactory.from_env()


def create_summary_client_from_env(
    *,
    deepseek_api_key: str | None = None,
    deepseek_model: str | None = None,
    deepseek_base_url: str | None = None,
) -> LLMClient | None:
    """摘要 / 精排链路统一的客户端选择入口。

    优先级：
    1. LLM_MODEL='provider/model'（支持 anthropic / deepseek / claude-code，走 ClientFactory）；
    2. CLAUDE_CODE_OAUTH_TOKEN 已配置（或 DPR_USE_CLAUDE_CODE=1 使用本机登录）
       → Claude Code CLI，消耗 Pro/Max 订阅额度（模型取 CLAUDE_CODE_MODEL，可留空）；
    3. ANTHROPIC_API_KEY 已配置 → Claude API（模型取 ANTHROPIC_MODEL，默认 claude-opus-4-8）；
    4. DeepSeek（沿用各步骤原有 DEEPSEEK_* / SUMMARY_* 环境变量）；
    5. 都没有 → 返回 None，由调用方决定跳过或报错。
    """
    model_env = (os.getenv('LLM_MODEL') or '').strip()
    if model_env:
        return ClientFactory.from_env()

    claude_code_token = (os.getenv('CLAUDE_CODE_OAUTH_TOKEN') or '').strip()
    use_claude_code = (os.getenv('DPR_USE_CLAUDE_CODE') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    if claude_code_token or use_claude_code:
        cli_model = (os.getenv('CLAUDE_CODE_MODEL') or '').strip()
        return ClaudeCodeClient(oauth_token=claude_code_token, model=cli_model)

    anthropic_key = (os.getenv('ANTHROPIC_API_KEY') or '').strip()
    if anthropic_key:
        model = (os.getenv('ANTHROPIC_MODEL') or '').strip() or DEFAULT_ANTHROPIC_MODEL
        base_url = (os.getenv('ANTHROPIC_BASE_URL') or '').strip() or None
        return AnthropicClient(api_key=anthropic_key, model=model, base_url=base_url)

    api_key = (
        deepseek_api_key
        or os.getenv('DEEPSEEK_API_KEY')
        or os.getenv('SUMMARY_API_KEY')
        or ''
    ).strip()
    if not api_key:
        return None
    model = (
        deepseek_model
        or os.getenv('SUMMARY_MODEL')
        or os.getenv('DEEPSEEK_MODEL')
        or 'deepseek-v4-flash'
    ).strip()
    base_url = (
        deepseek_base_url
        or os.getenv('DEEPSEEK_BASE_URL')
        or os.getenv('SUMMARY_BASE_URL')
        or DEFAULT_DEEPSEEK_BASE_URL
    ).strip()
    return DeepSeekClient(api_key=api_key, model=model, base_url=base_url)
