"""全局配置：数据库连接、LLM 端点、管道开关。

所有配置都可用环境变量覆盖，便于在本地 / 内网服务器 / 容器中切换，
无需改代码。复制 .env.example 为 .env 后按需修改。
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------- 数据库（PostgreSQL + pgvector） ----------
DB_DSN = os.getenv(
    "DB_DSN",
    "postgresql://postgres:postgres@localhost:5432/question_bank",
)

# ---------- LLM（OpenAI 兼容接口） ----------
# 本地：vLLM 默认监听 http://localhost:8000/v1
# 云端：豆包 / DeepSeek 等 OpenAI 兼容服务，填对应 base_url 和 key
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "EMPTY")
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-14B-Instruct")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

# ---------- 文档解析 ----------
# PDF 无文本层（扫描件）时是否启用 OCR；纯文本 PDF 无需 OCR
OCR_FALLBACK = os.getenv("OCR_FALLBACK", "1") == "1"
# 公式识别（pix2tex / LaTeX-OCR）：数学科建议开启，需单独安装，见 README
FORMULA_OCR_ENABLED = os.getenv("FORMULA_OCR_ENABLED", "0") == "1"

# ---------- 向量化（可选） ----------
# 先不装 sentence-transformers 也能完成入库，只是暂时没有语义检索向量
EMBEDDING_ENABLED = os.getenv("EMBEDDING_ENABLED", "1") == "1"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")  # 输出 1024 维

# ---------- 管道参数 ----------
# 每份文档切分后的文本块批量送 LLM 解析
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "8"))
# 支持的输入文件类型
SUPPORTED_EXTS = {".docx", ".pdf", ".png", ".jpg", ".jpeg"}
# 知识点候选词表文件（可选，用于约束 LLM 的知识点输出）
KP_DICT_FILE = os.getenv("KP_DICT_FILE", "")

# 内置知识点候选（先用粗粒度词表跑通，正式使用请按校本科目扩充或换文件）
DEFAULT_KNOWLEDGE_POINTS = {
    "数学": ["有理数", "整式加减", "一元一次方程", "二元一次方程组", "不等式",
             "相交线与平行线", "三角形", "全等三角形", "轴对称", "勾股定理",
             "实数", "二次根式", "一次函数", "二次函数", "反比例函数",
             "平行四边形", "圆", "相似", "锐角三角函数", "统计与概率"],
    "语文": ["拼音", "字词", "成语", "修辞", "病句", "标点", "文学常识",
             "古诗词默写", "文言文阅读", "现代文阅读", "说明文阅读", "议论文阅读",
             "作文", "口语交际", "名著阅读"],
    "英语": ["名词", "代词", "冠词", "数词", "形容词", "副词", "介词",
             "动词时态", "被动语态", "非谓语动词", "情态动词", "连词",
             "宾语从句", "定语从句", "状语从句", "情景交际", "完形填空", "阅读理解"],
}


def get_knowledge_points(subject: str) -> list[str]:
    """返回某科目的知识点候选词表，用于约束 LLM 输出。"""
    if KP_DICT_FILE:
        try:
            text = Path(KP_DICT_FILE).read_text(encoding="utf-8")
            return [ln.strip() for ln in text.splitlines() if ln.strip()]
        except OSError:
            pass
    return DEFAULT_KNOWLEDGE_POINTS.get(subject, [])
