# 智能题库 · P1 文档解析与题目入库

把本地服务器的中小学试卷文档（Word / PDF / 扫描图片，人教版、北师大版等）
自动解析成**结构化题库**，为后续「按学生成绩等级智能组卷」打地基。

## 目录结构

```
question-bank/
├── run_pipeline.py          # 管道入口（扫描目录 → 入库）
├── config/settings.py       # 配置（数据库 / LLM / 开关），支持环境变量覆盖
├── pipeline/
│   ├── extract_text.py      # 文档文本提取：docx/pdf(文本层或OCR)/图片
│   ├── prompts.py           # LLM 抽取提示词 + JSON Schema
│   ├── llm_extract.py       # LLM 结构化抽取（OpenAI 兼容接口 + 重试）
│   ├── validate.py          # 规则校验（题型/难度/选项/答案）+ 去重指纹
│   └── ingest.py            # 入库：questions / 知识点 / 关联 / 日志 / 向量
├── sql/schema.sql           # 数据表 DDL（PostgreSQL + pgvector）
├── tests/test_validate.py   # 校验与切块单测（无需外部依赖）
├── docker-compose.yml       # 一键起 PostgreSQL + pgvector
├── requirements.txt         # Python 依赖
└── .env.example             # 环境变量示例
```

## 运行前准备

```bash
# 1. 启动数据库
docker compose up -d

# 2. 建表
psql "postgresql://postgres:postgres@localhost:5432/question_bank" -f sql/schema.sql

# 3. 安装 Python 依赖（扫描件需要 OCR 再装注释里的 paddle 两个包）
pip install -r requirements.txt

# 4. 确认 LLM 服务可用（任一 OpenAI 兼容服务即可）
#    本地示例：vllm serve Qwen/Qwen2.5-14B-Instruct --port 8000
#    云端示例：export LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3 LLM_API_KEY=xxx LLM_MODEL=xxx
```

## 使用

```bash
# 单份文件入库
python run_pipeline.py --file /data/试卷/2024期末数学卷.docx \
    --subject 数学 --grade 七年级 --version 人教版

# 整个目录批量入库（递归扫描 docx/pdf/png/jpg）
python run_pipeline.py --dir /data/试卷 \
    --subject 数学 --grade 七年级 --version 人教版

# 只解析不落库（调试）：写出 <文件名>.parsed.json
python run_pipeline.py --file x.pdf --subject 数学 --grade 七年级 --version 人教版 --dry-run
```

## 管道流程

```
原始文档 → 提取文本(Word/PDF文本层/OCR) → 按题号切块 → LLM 结构化抽取(JSON)
         → 规则校验 + 指纹去重 → 入库(questions + 知识点 + 向量) → ingest_logs
```

- 单文件失败只记录 `source_files.status=failed`，不影响整批继续。
- 同一题目重复出现（跨卷同题）由 `content_hash` 自动去重，不会重复入库。
- 知识点按 `(科目, 名称)` 幂等写入，人教/北师大版本可映射到同一知识点 ID。

## 入库后验证

```sql
-- 各科题目数量
SELECT subject, grade, textbook_version, question_type, count(*)
FROM questions GROUP BY 1,2,3,4 ORDER BY 1,2;

-- 最近一次入库日志
SELECT * FROM ingest_logs ORDER BY id DESC LIMIT 10;

-- 抽样检查某份文档的题目
SELECT id, question_type, difficulty, left(stem, 60) AS stem
FROM questions WHERE source_file_id = 1 LIMIT 20;
```

## 质量保障（P1 阶段）

| 环节 | 手段 |
|---|---|
| 结构化正确率 | LLM + JSON Schema 强约束；**人工抽检 ≥5%**，失败样本回流修 prompt |
| 去重 | content_hash（题型+题干+选项+答案）唯一约束 |
| 公式 | 统一 LaTeX 存储；建议 P1 后期接入 pix2tex 公式识别并抽检 |
| 溯源 | 每题记录 source_file_id / source_ref，可回查原卷 |

## 下一步（P2 / P3，不在本骨架内）

- P2 组卷引擎：OR-Tools 约束求解（总分/题型/难度配比精确满足）
- P3 个性化：成绩等级 → 难度配比映射、知识点弱项加权、平行卷
- 难度校准：积累答题数据后用 IRT 修正 difficulty 字段
