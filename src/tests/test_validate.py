"""validate.py 与 extract_text.py 的单元测试（纯标准库，无需外部依赖）。

运行：python -m pytest tests/ -v   或   python tests/test_validate.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.extract_text import split_blocks  # noqa: E402
from pipeline.validate import (  # noqa: E402
    content_hash,
    normalize_stem,
    validate_question,
)


def test_validate_question_ok():
    q = {
        "question_type": "选择",
        "difficulty": 3,
        "stem": "下列哪个数是质数？",
        "options": ["A. 4", "B. 6", "C. 7", "D. 8"],
        "answer": "C",
        "analysis": "7 只能被 1 和自身整除。",
        "knowledge_points": ["有理数"],
    }
    assert validate_question(q) == []


def test_validate_question_empty_stem():
    q = {"question_type": "选择", "difficulty": 3, "stem": "  ",
         "options": ["A. 1", "B. 2"], "answer": "A"}
    errors = validate_question(q)
    assert "题干为空" in errors


def test_validate_question_bad_difficulty():
    q = {"question_type": "填空", "difficulty": 7, "stem": "x=?"}
    errors = validate_question(q)
    assert any("难度" in e for e in errors)


def test_validate_question_bad_type():
    q = {"question_type": "简答", "difficulty": 2, "stem": "x=?"}
    errors = validate_question(q)
    assert any("题型" in e for e in errors)


def test_validate_choice_answer_out_of_options():
    q = {"question_type": "选择", "difficulty": 2, "stem": "1+1=?",
         "options": ["A. 1", "B. 2"], "answer": "D"}
    errors = validate_question(q)
    assert any("不在选项" in e for e in errors)


def test_validate_fill_answer_any_text_ok():
    q = {"question_type": "填空", "difficulty": 1, "stem": "1+1=____",
         "answer": "2"}
    assert validate_question(q) == []


def test_content_hash_stable_and_different():
    a = {"question_type": "选择", "stem": "1+1=?", "options": ["A. 1", "B. 2"], "answer": "B"}
    b = {"question_type": "选择", "stem": " 1＋1＝? ", "options": ["A. 1", "B. 2"], "answer": "B"}
    c = {"question_type": "选择", "stem": "1+2=?", "options": ["A. 1", "B. 3"], "answer": "B"}
    assert content_hash(a) == content_hash(b)   # 全角/空白被规范化
    assert content_hash(a) != content_hash(c)   # 题干不同则指纹不同


def test_normalize_stem():
    assert normalize_stem(" 1＋1＝? ") == normalize_stem("1+1=?")


def test_split_blocks():
    text = """1. 计算：2+3=?

2. 填空：x-1=0，x=____

3. 下列正确的是（  ）
A. 1>2
B. 2>1"""
    blocks = split_blocks(text)
    assert len(blocks) == 3
    assert blocks[0].startswith("1.")
    assert blocks[2].startswith("3.")


def test_split_blocks_no_number():
    text = "这是没有题号的说明文字。"
    assert split_blocks(text) == [text]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
