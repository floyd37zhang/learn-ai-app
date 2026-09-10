import os

class Config:
    """配置类"""
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "api-key")
    OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    OPENAI_API_MODEL = os.getenv("OPENAI_API_MODEL", "gpt-4o-mini")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    
    # Chroma 数据库配置
    CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
    
    # RAG 配置
    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 50
    TOP_K = 4
