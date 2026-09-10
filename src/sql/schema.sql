-- ============================================================
-- 智能题库 P1：题目入库数据模型
-- 数据库：PostgreSQL 16 + pgvector（docker-compose 已内置）
-- 用法：psql "$DB_DSN" -f sql/schema.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------- 来源文档表：记录每份被解析的原始试卷 ----------
CREATE TABLE IF NOT EXISTS source_files (
    id              BIGSERIAL PRIMARY KEY,
    file_path       TEXT NOT NULL UNIQUE,          -- 本地绝对路径，唯一约束防止重复入库
    file_type       TEXT NOT NULL,                 -- docx / pdf / png / jpg ...
    subject         TEXT,                          -- 数学 / 语文 / 英语
    grade           TEXT,                          -- 七年级 / 三年级 ...
    textbook_version TEXT,                         -- 人教版 / 北师大版 / 苏教版 ...
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'parsed', 'extracted', 'imported', 'failed')),
    error_msg       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- 知识点表：跨版本统一的知识点主数据 ----------
-- 不同教材版本对同一知识点命名不同，入库时统一映射到同一 name，
-- 组卷时按"知识点 ID"出题即可跨版本混用。
CREATE TABLE IF NOT EXISTS knowledge_points (
    id          BIGSERIAL PRIMARY KEY,
    subject     TEXT NOT NULL,
    grade       TEXT,
    name        TEXT NOT NULL,                     -- 如"一元一次方程"
    parent_id   BIGINT REFERENCES knowledge_points(id),
    UNIQUE (subject, name)
);

-- ---------- 题目表：结构化题库核心表 ----------
CREATE TABLE IF NOT EXISTS questions (
    id               BIGSERIAL PRIMARY KEY,
    source_file_id   BIGINT REFERENCES source_files(id),
    content_hash     TEXT NOT NULL UNIQUE,         -- 题型+题干+选项+答案 指纹，去重键
    subject          TEXT NOT NULL,
    grade            TEXT,
    textbook_version TEXT,                         -- 原卷版本（组卷筛选用）
    question_type    TEXT NOT NULL,                -- 选择 / 填空 / 解答 / 判断 / 计算 / 作图
    difficulty       SMALLINT NOT NULL CHECK (difficulty BETWEEN 1 AND 5),  -- 1 最易 5 最难
    stem             TEXT NOT NULL,                -- 题干（文本 + LaTeX 公式）
    options          JSONB,                        -- 选择题选项数组 ["A. ...", "B. ...", ...]
    answer           TEXT,                         -- 选择题为选项字母；填空/解答为答案文本
    analysis         TEXT,                         -- 解析（LLM 生成，可后续人工修订）
    source_ref       TEXT,                         -- 溯源信息，如 "2024期末卷.docx P3"
    status           TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active', 'review', 'disabled')),
    embedding        vector(1024),                 -- bge-m3 题干语义向量（可选列）
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_questions_type      ON questions (question_type);
CREATE INDEX IF NOT EXISTS idx_questions_subject   ON questions (subject, grade, textbook_version);
CREATE INDEX IF NOT EXISTS idx_questions_difficulty ON questions (difficulty);

-- ---------- 题目-知识点 多对多 ----------
CREATE TABLE IF NOT EXISTS question_kp (
    question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    kp_id       BIGINT NOT NULL REFERENCES knowledge_points(id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, kp_id)
);

-- ---------- 入库日志：每次管道运行的结果留痕 ----------
CREATE TABLE IF NOT EXISTS ingest_logs (
    id              BIGSERIAL PRIMARY KEY,
    source_file_id  BIGINT REFERENCES source_files(id),
    total_questions INT NOT NULL DEFAULT 0,
    success_count   INT NOT NULL DEFAULT 0,
    fail_count      INT NOT NULL DEFAULT 0,
    detail          JSONB,                         -- 失败题目明细 [{index, errors}]
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
