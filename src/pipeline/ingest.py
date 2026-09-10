"""入库模块：source_files / questions / knowledge_points / question_kp / ingest_logs。

关键点：
- 所有 SQL 均用参数化查询，杜绝注入
- questions 以 content_hash 唯一约束去重（ON CONFLICT DO NOTHING）
- 知识点按 (subject, name) upsert，跨教材版本统一
- embedding 可选：未安装 sentence-transformers 时自动跳过，不影响入库
"""
import json
import logging
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # 延迟报错：--dry-run / 静态分析不应因缺依赖崩溃
    psycopg = None  # type: ignore
    dict_row = None  # type: ignore

from config import settings  # noqa: E402  项目根已在 run_pipeline.py 加入 sys.path
from pipeline.validate import content_hash, validate_question  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------- SQL 常量 ----------------

SQL_UPSERT_SOURCE = """
INSERT INTO source_files (file_path, file_type, subject, grade, textbook_version, status)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (file_path) DO UPDATE
SET status = EXCLUDED.status, subject = EXCLUDED.subject,
    grade = EXCLUDED.grade, textbook_version = EXCLUDED.textbook_version,
    error_msg = NULL, updated_at = now()
RETURNING id
"""

SQL_UPDATE_SOURCE_STATUS = """
UPDATE source_files SET status = %s, error_msg = %s, updated_at = now() WHERE id = %s
"""

SQL_UPSERT_KP = """
INSERT INTO knowledge_points (subject, grade, name)
VALUES (%s, %s, %s)
ON CONFLICT (subject, name) DO UPDATE
SET grade = EXCLUDED.grade
RETURNING id
"""

SQL_INSERT_QUESTION = """
INSERT INTO questions
    (source_file_id, content_hash, subject, grade, textbook_version,
     question_type, difficulty, stem, options, answer, analysis, source_ref, status)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active')
ON CONFLICT (content_hash) DO NOTHING
RETURNING id
"""

SQL_LINK_KP = """
INSERT INTO question_kp (question_id, kp_id) VALUES (%s, %s) ON CONFLICT DO NOTHING
"""

SQL_UPDATE_EMBEDDING = """
UPDATE questions SET embedding = %s WHERE id = %s
"""

SQL_INSERT_LOG = """
INSERT INTO ingest_logs (source_file_id, total_questions, success_count, fail_count, detail)
VALUES (%s, %s, %s, %s, %s)
"""

# ---------------- 基础操作 ----------------


def get_conn() -> "psycopg.Connection":
    """建立数据库连接（行以 dict 返回）。"""
    if psycopg is None:
        raise RuntimeError("缺少依赖：pip install 'psycopg[binary]'")
    return psycopg.connect(settings.DB_DSN, row_factory=dict_row)


def upsert_source_file(
    conn: "psycopg.Connection",
    file_path: str,
    file_type: str,
    subject: str,
    grade: str,
    textbook_version: str,
) -> int:
    """登记/更新来源文档，返回 source_files.id。"""
    with conn.cursor() as cur:
        cur.execute(
            SQL_UPSERT_SOURCE,
            (file_path, file_type, subject, grade, textbook_version, "parsed"),
        )
        row = cur.fetchone()
        return int(row["id"])


def update_source_status(
    conn: "psycopg.Connection", source_file_id: int, status: str, error_msg: str = ""
) -> None:
    """更新来源文档处理状态（parsed/extracted/imported/failed）。"""
    with conn.cursor() as cur:
        cur.execute(
            SQL_UPDATE_SOURCE_STATUS, (status, error_msg or None, source_file_id)
        )
    conn.commit()


def _upsert_kp(conn: "psycopg.Connection", name: str, subject: str, grade: str) -> int:
    """按 (subject, name) 幂等写入知识点，返回 id。"""
    with conn.cursor() as cur:
        cur.execute(SQL_UPSERT_KP, (subject, grade, name))
        return int(cur.fetchone()["id"])


# ---------------- 单文件入库 ----------------


def ingest_parsed_document(
    conn: "psycopg.Connection",
    source_file_id: int,
    parsed: dict[str, Any],
    source_ref: str = "",
) -> dict[str, Any]:
    """把 LLM 解析结果写入题库。

    参数:
        conn: 数据库连接
        source_file_id: source_files.id
        parsed: {"subject", "grade", "textbook_version", "questions": [...]}
        source_ref: 溯源信息（如文件名+页码）

    返回:
        {"total": n, "success": n, "fail": n, "failed": [ {index, errors} ]}
    """
    subject = parsed.get("subject") or ""
    grade = parsed.get("grade") or ""
    version = parsed.get("textbook_version") or ""
    questions = parsed.get("questions") or []

    result = {"total": len(questions), "success": 0, "fail": 0, "failed": []}

    for idx, q in enumerate(questions):
        errors = validate_question(q)
        if errors:
            result["fail"] += 1
            result["failed"].append({"index": idx, "errors": errors})
            continue

        h = content_hash(q)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    SQL_INSERT_QUESTION,
                    (
                        source_file_id, h, subject, grade, version,
                        q["question_type"], int(q["difficulty"]),
                        q["stem"], json.dumps(q.get("options") or [], ensure_ascii=False),
                        q.get("answer") or "", q.get("analysis") or "", source_ref,
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    # 已存在同指纹题目（去重），计入成功但不再关联
                    result["success"] += 1
                    continue
                question_id = int(row["id"])

                # 关联知识点（自动建库）
                for kp_name in q.get("knowledge_points") or []:
                    kp_name = (kp_name or "").strip()
                    if not kp_name:
                        continue
                    kp_id = _upsert_kp(conn, kp_name, subject, grade)
                    cur.execute(SQL_LINK_KP, (question_id, kp_id))

                # 写入语义向量（可选）
                vec = _embed(conn, q)
                if vec is not None:
                    cur.execute(SQL_UPDATE_EMBEDDING, (vec, question_id))

            result["success"] += 1
        except Exception as e:  # 单题失败不影响整份文档
            logger.exception("题目入库失败 index=%s: %s", idx, e)
            result["fail"] += 1
            result["failed"].append({"index": idx, "errors": [f"db error: {e}"]})

    conn.commit()
    return result


def write_ingest_log(
    conn: "psycopg.Connection",
    source_file_id: int,
    result: dict[str, Any],
) -> None:
    """把本次入库结果写入 ingest_logs。"""
    with conn.cursor() as cur:
        cur.execute(
            SQL_INSERT_LOG,
            (
                source_file_id,
                result["total"],
                result["success"],
                result["fail"],
                json.dumps(result["failed"], ensure_ascii=False),
            ),
        )
    conn.commit()


# ---------------- 向量化（可选） ----------------

_embedder = None


def _get_embedder():
    """懒加载 bge-m3；未安装或配置关闭时返回 None。"""
    global _embedder
    if _embedder is not None:
        return _embedder
    if not settings.EMBEDDING_ENABLED:
        return None
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        logger.warning(
            "未安装 sentence-transformers，跳过 embedding（不影响入库）。"
            "安装后重启即可启用语义检索：pip install sentence-transformers"
        )
        _embedder = False
        return None
    logger.info("加载 embedding 模型: %s", settings.EMBEDDING_MODEL)
    _embedder = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _embedder


def _embed(conn: "psycopg.Connection", q: dict) -> list[float] | None:
    """把单题题干+选项编码为向量。向量格式按 pgvector 要求返回 list[float]。"""
    model = _get_embedder()
    if model is None:
        return None
    text = q.get("stem", "") + " " + " ".join(q.get("options") or [])
    if not text.strip():
        return None
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()
