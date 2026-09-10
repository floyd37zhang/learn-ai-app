"""P1 管道入口：一份/一个目录的试卷文档 → 结构化题目入库。

用法：
    # 单份文件（用命令行元数据覆盖文档内信息）
    python run_pipeline.py --file /data/试卷/2024期末数学卷.docx \
        --subject 数学 --grade 七年级 --version 人教版

    # 整目录批量（目录下所有 docx/pdf/图片）
    python run_pipeline.py --dir /data/试卷 --subject 数学 --grade 七年级 --version 人教版

    # 只输出文本/JSON 不落库（调试用）
    python run_pipeline.py --file x.docx --dry-run

流程：登记 source_files → 提取文本 → 按题号切块 → LLM 分批抽取 →
      规则校验 + 指纹去重 → 入库 → 写 ingest_logs。
单文件失败只记录状态，不中断整批。
"""
import argparse
import json
import logging
import sys
from pathlib import Path

# 允许从项目根目录直接运行：python run_pipeline.py
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import settings  # noqa: E402
from pipeline import extract_text, ingest, llm_extract  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_pipeline")


def _collect_files(path: Path) -> list[Path]:
    """收集待处理文件：单文件或目录内受支持类型。"""
    if path.is_file():
        return [path]
    files = sorted(
        p for p in path.rglob("*")
        if p.suffix.lower() in settings.SUPPORTED_EXTS
    )
    return files


def _process_one(
    client,
    conn,
    file_path: Path,
    subject: str,
    grade: str,
    version: str,
    dry_run: bool = False,
) -> dict:
    """处理单份文档，返回处理摘要。"""
    logger.info("开始处理: %s", file_path)
    summary = {"file": str(file_path), "ok": False, "detail": ""}

    # 1. 登记来源文档
    source_id = None
    if not dry_run:
        source_id = ingest.upsert_source_file(
            conn, str(file_path), file_path.suffix.lower().lstrip("."),
            subject, grade, version,
        )

    try:
        # 2. 提取文本
        text = extract_text.extract_text(
            file_path, ocr_fallback=settings.OCR_FALLBACK
        )
        if not text.strip():
            raise ValueError("提取文本为空（可能是纯扫描件且 OCR 未生效）")

        # 3. 按题号切块，分批送 LLM
        blocks = extract_text.split_blocks(text)
        logger.info("切分为 %d 个文本块", len(blocks))
        kps = settings.get_knowledge_points(subject)

        all_questions: list[dict] = []
        for i in range(0, len(blocks), settings.BATCH_SIZE):
            batch = blocks[i:i + settings.BATCH_SIZE]
            for j, block in enumerate(batch):
                parsed = llm_extract.extract_questions(
                    client,
                    model=settings.LLM_MODEL,
                    subject=subject,
                    grade=grade,
                    textbook_version=version,
                    knowledge_points=kps,
                    page_text=block,
                    max_retries=settings.LLM_MAX_RETRIES,
                    timeout=settings.LLM_TIMEOUT,
                )
                qs = parsed.get("questions") or []
                all_questions.extend(qs)
                logger.info(
                    "块 %d/%d 抽取 %d 题（累计 %d）",
                    i + j + 1, len(blocks), len(qs), len(all_questions),
                )

        merged = {
            "subject": subject, "grade": grade,
            "textbook_version": version, "questions": all_questions,
        }

        if dry_run:
            out = file_path.with_suffix(file_path.suffix + ".parsed.json")
            out.write_text(
                json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            summary.update(ok=True, detail=f"dry-run 已写出 {out}")
            return summary

        # 4. 入库 + 日志
        result = ingest.ingest_parsed_document(
            conn, source_id, merged, source_ref=f"{file_path.name}"
        )
        ingest.write_ingest_log(conn, source_id, result)
        ingest.update_source_status(
            conn, source_id,
            "imported" if result["fail"] == 0 else "extracted",
        )

        summary.update(
            ok=True,
            detail=(
                f"共 {result['total']} 题，入库 {result['success']}，"
                f"失败 {result['fail']}"
            ),
        )
        if result["failed"]:
            summary["detail"] += "；失败明细: " + json.dumps(
                result["failed"][:5], ensure_ascii=False
            )
        return summary

    except Exception as e:
        logger.exception("处理失败: %s", file_path)
        if not dry_run:
            ingest.update_source_status(conn, source_id, "failed", str(e))
        summary["detail"] = f"error: {e}"
        return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="试卷文档 → 结构化题库入库")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", type=Path, help="单份试卷文件")
    src.add_argument("--dir", type=Path, help="试卷目录（递归）")
    parser.add_argument("--subject", required=True, help="科目：数学/语文/英语")
    parser.add_argument("--grade", required=True, help="年级：如 七年级")
    parser.add_argument("--version", required=True, help="教材版本：如 人教版")
    parser.add_argument("--dry-run", action="store_true", help="只解析不落库，写出 .parsed.json")
    args = parser.parse_args(argv)

    target = args.file or args.dir
    files = _collect_files(target)
    if not files:
        logger.error("没有找到可处理的文件: %s", target)
        return 2
    logger.info("共 %d 个文件待处理", len(files))

    try:
        client = llm_extract.build_client(settings.LLM_BASE_URL, settings.LLM_API_KEY)
    except RuntimeError as e:
        logger.error("%s。请先执行: pip install -r requirements.txt", e)
        return 2
    conn = None if args.dry_run else ingest.get_conn()

    ok_count = 0
    for f in files:
        summary = _process_one(
            client, conn, f, args.subject, args.grade, args.version, args.dry_run
        )
        logger.info("[%s] %s", "OK" if summary["ok"] else "FAIL", summary["detail"])
        ok_count += 1 if summary["ok"] else 0

    if conn is not None:
        conn.close()
    logger.info("完成：%d/%d 成功", ok_count, len(files))
    return 0 if ok_count == len(files) else 1


if __name__ == "__main__":
    raise SystemExit(main())
