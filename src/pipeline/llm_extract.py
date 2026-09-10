"""LLM 结构化抽取：把试卷文本块转换为结构化题目 JSON。

- 兼容 OpenAI 接口（本地 vLLM / Ollama / 豆包 / DeepSeek 均可）
- response_format=json_object 强制 JSON 输出
- 失败自动重试（指数退避），仍失败抛 ExtractError 交由上层记录
- 如你的 LLM 服务支持 json_schema 模式，可把 response_format 升级为
  {"type": "json_schema", "json_schema": {...EXTRACT_SCHEMA...}} 做结构强校验
"""
import json
import logging
import time

try:
    from openai import OpenAI
except ImportError:  # 延迟报错：--help / 静态分析不应因缺依赖崩溃
    OpenAI = None  # type: ignore

from .prompts import (
    EXTRACT_SCHEMA,          # noqa: F401  供外部按需使用
    EXTRACT_SYSTEM_PROMPT,
    EXTRACT_USER_PROMPT_TEMPLATE,
)

logger = logging.getLogger(__name__)


class ExtractError(RuntimeError):
    """LLM 抽取失败（重试后仍失败）。"""


def build_client(base_url: str, api_key: str) -> OpenAI:
    """创建 OpenAI 兼容客户端。"""
    if OpenAI is None:
        raise RuntimeError("缺少依赖：pip install openai")
    return OpenAI(base_url=base_url, api_key=api_key)


def extract_questions(
    client: OpenAI,
    model: str,
    subject: str,
    grade: str,
    textbook_version: str,
    knowledge_points: list[str],
    page_text: str,
    max_retries: int = 2,
    timeout: int = 120,
) -> dict:
    """把一段试卷文本抽取为结构化 JSON。

    返回形如：
    {
      "subject": "数学", "grade": "七年级", "textbook_version": "人教版",
      "questions": [ {...}, ... ]
    }
    """
    prompt = EXTRACT_USER_PROMPT_TEMPLATE.format(
        subject=subject,
        grade=grade,
        textbook_version=textbook_version,
        knowledge_points="、".join(knowledge_points) if knowledge_points else "（未提供，请按课标常用表述）",
        page_text=page_text,
    )

    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                timeout=timeout,
            )
            content = resp.choices[0].message.content or ""
            data = json.loads(content)
            if not isinstance(data, dict) or "questions" not in data:
                raise ExtractError("返回 JSON 缺少 questions 数组")
            if not isinstance(data["questions"], list):
                raise ExtractError("questions 字段不是数组")
            return data
        except (json.JSONDecodeError, ExtractError) as e:
            last_err = e
            logger.warning("抽取失败（第 %d 次尝试）: %s", attempt + 1, e)
        except Exception as e:  # 网络/服务错误
            last_err = e
            logger.warning("LLM 调用异常（第 %d 次尝试）: %s", attempt + 1, e)
        if attempt < max_retries:
            time.sleep(2 * (attempt + 1))

    raise ExtractError(f"LLM 抽取失败: {last_err}") from last_err
