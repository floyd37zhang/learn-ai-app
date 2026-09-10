from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter, CharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from config import Config


def build_vector_store(doc_path: str, store_path: str):
    """
    加载文档并构建向量数据库
    """
    loader = TextLoader(doc_path, encoding="utf-8")
    docs = loader.load()
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=Config.CHUNK_SIZE,
        chunk_overlap=Config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "！", "？", " ", " ", ""],
    )
    docs = text_splitter.split_documents(docs)
    
    embeddings = OpenAIEmbeddings(
        model_name=Config.EMBEDDING_MODEL,
        api_key=Config.OPENAI_API_KEY,
        api_base=Config.OPENAI_API_BASE,
    )
    
    vector_store = Chroma.from_documents(
        documents=docs,
        embedding_function=embeddings,
        persist_directory=store_path,
    )
    
    return vector_store


def get_retriever(store_path: str):
    """
    获取向量数据库的检索器
    """
    embedding_model = OpenAIEmbeddings(
        model_name=Config.EMBEDDING_MODEL,
        api_key=Config.OPENAI_API_KEY,
        api_base=Config.OPENAI_API_BASE,
    )
    vector_store = Chroma(
        persist_directory=store_path,
        embedding_function=embedding_model,
    )
    
    return vector_store.as_retriever(search_kwargs={"k": Config.K})
