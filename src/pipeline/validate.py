"""题目规则校验与去重指纹。

LLM 输出不能直接入库：先过一遍确定性规则（题干非空、题型合法、
难度范围、选择题答案合法性），再用指纹去重，保证题库质量与唯一性。
"""
import hashlib
import re
import unicodedata

VALID_TYPES = {"选择", "填空", "解答", "判断", "计算", "作图"}
OPTION_LETTERS = {"A", "B", "C", "D", "E", "F"}


def validate_question(q: dict) -> list[str]:
    """校验单道题，返回错误列表（空列表 = 通过）。

    规则：
    - 题型必须在合法集合内
    - 难度必须是 1-5 整数
    - 题干非空
    - 选择题/判断题必须有选项且答案必须是选项字母
    """
    errors: list[str] = []

    qtype = q.get("question_type")
    if qtype not in VALID_TYPES:
        errors.append(f"未知题型: {qtype!r}")

    diff = q.get("difficulty")
    if not isinstance(diff, int) or isinstance(diff, bool) or not (1 <= diff <= 5):
        errors.append(f"难度必须是 1-5 的整数: {diff!r}")

    stem = (q.get("stem") or "").strip()
    if not stem:
        errors.append("题干为空")

    if qtype in {"选择", "判断"}:
        options = q.get("options") or []
        if not isinstance(options, list) or not options:
            errors.append("选择题/判断题缺少选项")
        answer = (q.get("answer") or "").strip().upper()
        if answer not in OPTION_LETTERS:
            errors.append(f"选择题/判断题答案必须是选项字母 A-F: {answer!r}")
        # 答案字母必须存在于选项编号范围内（如只有 A B，答案就不能是 D）
        letters = {opt.split(".")[0].strip() for opt in options if "." in opt}
        if letters and answer and answer not in letters:
            errors.append(f"答案 {answer} 不在选项 {sorted(letters)} 中")

    return errors


def normalize_stem(text: str) -> str:
    """规范化题干文本：全角→半角（NFKC）+ 去空白，用于指纹与比对。

    NFKC 会把全角 ＋＝？（）． 等统一为半角 + = ? ( ) . ，
    同时不影响汉字本身。
    """
    t = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", "", t)


def content_hash(question: dict) -> str:
    """基于 题型+题干+选项+答案 生成去重指纹（SHA-256）。"""
    key = "|".join([
        str(question.get("question_type", "")),
        normalize_stem(question.get("stem", "")),
        "".join(question.get("options") or []),
        str(question.get("answer", "")),
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
