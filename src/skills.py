from langchain_core.tools import tool
from retriever import get_retriever
from config import Config

_retriever = get_retriever(Config.CHROMA_DB_PATH)


@tool
def search_knowledge_base(query: str) -> str:
    """当用户询问关于员工手册的问题时，搜索知识库获取相关信息"""
    docs = _retriever.invoke(query)
    if not docs:
        return "没有找到相关文档"
    
    return "\n\n".join([doc.page_content for doc in docs])
    
