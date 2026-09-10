"""文档文本提取模块：Word / PDF（文本层或 OCR 兜底）/ 图片 → 纯文本。

各函数职责单一：extract_text 按扩展名分发；_extract_* 负责具体格式；
split_blocks 把长文本按题号粗切分，供 LLM 批量解析。

依赖（见 requirements.txt）：
- python-docx：.docx
- PyMuPDF (fitz)：.pdf
- PaddleOCR：扫描版 PDF / 图片（可选，未安装时自动降级并提示）

注意：PaddleOCR 首次运行会下载模型权重，且较重；纯文本 PDF 和 Word
场景不需要它。
"""
import logging
import re
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# 题号正则：行首的 "1." / "1、" / "1．" / "1）" / "（1）"
_QUESTION_NO_RE = re.compile(r"(?m)^\s*(?:（|\(|\s*)(\d{1,3})\s*[.、．）)]\s*")

# 大题标题：一、二、三 ...（可选增强，后续可加）
_SECTION_RE = re.compile(r"(?m)^\s*[一二三四五六七八九十]+\s*[、.．]\s*")


def extract_text(path: str | Path, ocr_fallback: bool = True) -> str:
    """按扩展名分发，返回文档全文文本（UTF-8 字符串）。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix == ".pdf":
        return _extract_pdf(path, ocr_fallback)
    if suffix in (".png", ".jpg", ".jpeg"):
        return _extract_image(path)
    raise ValueError(f"不支持的文件类型: {suffix}（支持 docx/pdf/png/jpg/jpeg）")


def _extract_docx(path: Path) -> str:
    """Word：段落 + 表格单元格（试卷常用表格排版，务必抽取）。"""
    from docx import Document

    doc = Document(str(path))
    parts: list[str] = []
    for para in doc.paragraphs:
        t = para.text.strip()
        if t:
            parts.append(t)
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _extract_pdf(path: Path, ocr_fallback: bool) -> str:
    """PDF：优先取文本层；无文本层（扫描件）且允许时走 OCR。"""
    import fitz  # PyMuPDF

    pages: list[str] = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            t = page.get_text("text").strip()
            if t:
                pages.append(t)
    joined = "\n".join(pages)
    if joined.strip():
        return joined
    if not ocr_fallback:
        logger.warning("PDF 无文本层且 OCR 已关闭: %s", path)
        return ""
    logger.info("PDF 无文本层，转 OCR: %s", path)
    return _ocr_pdf(path)


def _ocr_pdf(path: Path) -> str:
    """扫描版 PDF：逐页渲染为图片后调用 PaddleOCR。"""
    import fitz

    ocr = _get_ocr()
    out: list[str] = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                pix.save(str(tmp_path))
                page_text = _ocr_image_path(ocr, tmp_path)
                if page_text.strip():
                    out.append(page_text)
            finally:
                tmp_path.unlink(missing_ok=True)
    return "\n".join(out)


def _extract_image(path: Path) -> str:
    """单张图片直接 OCR。"""
    return _ocr_image_path(_get_ocr(), path)


def _ocr_image_path(ocr, path: Path) -> str:
    """对单张图片执行 OCR，把识别结果拼成文本。"""
    result = ocr.ocr(str(path), cls=True)
    lines: list[str] = []
    # PaddleOCR 返回 [[ [box, (text, conf)], ... ], ...]
    for page in result or []:
        for line in page or []:
            if line and len(line) >= 2:
                text = line[1][0].strip() if isinstance(line[1], (list, tuple)) else ""
                if text:
                    lines.append(text)
    return "\n".join(lines)


_ocr = None


def _get_ocr():
    """懒加载单例 PaddleOCR（首次调用较慢）。"""
    global _ocr
    if _ocr is None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as e:  # pragma: no cover - 依赖缺失路径
            raise RuntimeError(
                "OCR 需要安装依赖：pip install paddlepaddle paddleocr，"
                "或对纯文本 PDF/Word 关闭 OCR_FALLBACK"
            ) from e
        _ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    return _ocr


def split_blocks(text: str, min_len: int = 5) -> list[str]:
    """把全文按题号切分为文本块，供 LLM 批量解析。

    规则：以行首数字编号（1. / 1、 / （1）等）为切分点。
    属于"粗切分"——复合大题（一、阅读下面的材料...）不会被切散，
    它们会作为一个块整体交给 LLM，由 LLM 拆出子题。
    """
    text = text.strip()
    if not text:
        return []
    matches = list(_QUESTION_NO_RE.finditer(text))
    if not matches:
        return [text] if len(text) >= min_len else []
    blocks: list[str] = []
    start = matches[0].start()
    for m in matches[1:]:
        blocks.append(text[start:m.start()].strip())
        start = m.start()
    blocks.append(text[start:].strip())
    return [b for b in blocks if len(b) >= min_len]
