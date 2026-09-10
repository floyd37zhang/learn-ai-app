"""LLM 结构化抽取的提示词与输出 JSON Schema。

核心思路：让 LLM 只做"把试卷文本翻译成 JSON"，不做任何自由发挥；
用 schema 强约束字段，再配合 validate.py 的规则校验兜底。
"""

EXTRACT_SYSTEM_PROMPT = """你是中小学试题入库专员。你的任务是把一段试卷文本拆解成结构化试题 JSON。

硬性要求：
1. 只输出一个合法 JSON 对象，禁止输出任何解释、前缀或后缀文字。
2. JSON 顶层必须包含 subject / grade / textbook_version / questions 四个字段。
3. questions 是数组，每道题包含字段：question_type、difficulty、stem、options、answer、analysis、knowledge_points。
4. question_type 只能是"选择"、"填空"、"解答"、"判断"、"计算"、"作图"之一，拿不准选最接近的类型。
5. difficulty 是 1-5 的整数：1 最易、5 最难，根据运算步骤数、知识点深度和常见考法判断。
6. 选择题/判断题必须给出完整 options（如 ["A. ...", "B. ...", "C. ...", "D. ..."]），answer 写选项字母（大写）；其余题型 answer 写答案文本，不确定可留空字符串。
7. stem / options / answer / analysis 中出现分数、根号、上标等数学符号时，一律用 LaTeX 行内公式表示，例如 $\\frac{1}{2}$、$\\sqrt{3}$、$x^{2}$。
8. knowledge_points 必须从用户给出的"可用知识点列表"中选择 1-3 个，不得编造列表外的知识点。
9. 如果文本块不是试题（如标题、目录、答案页说明），questions 输出空数组，不要硬造。
10. analysis 给出简要解题思路或答案依据；解答题尽量给出关键步骤。

以下是你必须遵守的输出结构：
{
  "subject": "科目",
  "grade": "年级",
  "textbook_version": "教材版本",
  "questions": [
    {
      "question_type": "选择",
      "difficulty": 3,
      "stem": "题干（含 $LaTeX$ 公式）",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "answer": "A",
      "analysis": "解析",
      "knowledge_points": ["知识点1", "知识点2"]
    }
  ]
}"""

EXTRACT_USER_PROMPT_TEMPLATE = """科目：{subject}
年级：{grade}
教材版本：{textbook_version}
可用知识点列表（只能从中选择）：{knowledge_points}

下面是待解析的试卷文本，请按系统要求输出 JSON：

{page_text}"""

# JSON Schema（目前作为文档与人工检查用；OpenAI 兼容接口用
# response_format={"type": "json_object"} 约束，schema 可扩展为
# json_schema 模式做更强校验，见 llm_extract.py 注释）
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "grade": {"type": "string"},
        "textbook_version": {"type": "string"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "question_type", "difficulty", "stem",
                    "options", "answer", "analysis", "knowledge_points",
                ],
                "properties": {
                    "question_type": {
                        "type": "string",
                        "enum": ["选择", "填空", "解答", "判断", "计算", "作图"],
                    },
                    "difficulty": {"type": "integer", "minimum": 1, "maximum": 5},
                    "stem": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "answer": {"type": "string"},
                    "analysis": {"type": "string"},
                    "knowledge_points": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
    "required": ["subject", "grade", "textbook_version", "questions"],
}
