"""
FastAPI RAG-сервис для платформы изучения японского языка.
Использует локальную Ollama (qwen2.5:7b) и Qdrant для семантического поиска.
"""

import os
import time
import logging
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# ==========================================
# 1. КОНФИГУРАЦИЯ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Настройки подключения
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "jp_learning_materials")

# Модель эмбеддингов (та же, что использовалась при ingestion)
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"

# Локальная Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL_NAME = os.getenv("LLM_MODEL", "qwen2.5:7b")

# ==========================================
# 2. PYDANTIC МОДЕЛИ (валидация запросов/ответов)
# ==========================================
class SourceMetadata(BaseModel):
    source: str
    score: float
    chunk_id: int

class RAGRequest(BaseModel):
    query: str = Field(
        ..., 
        min_length=3, 
        max_length=500,
        description="Вопрос ученика на русском или японском языке"
    )
    top_k: int = Field(default=3, ge=1, le=10, description="Количество чанков для поиска")
    include_sources: bool = Field(default=True, description="Включать ссылки на источники")
    temperature: float = Field(default=0.3, ge=0.0, le=1.0, description="Креативность LLM")

class RAGResponse(BaseModel):
    answer: str
    sources: Optional[List[SourceMetadata]] = None
    processing_time_ms: float
    model_used: str

# ==========================================
# 3. СИСТЕМНЫЙ ПРОМПТ ("Нежный учитель")
# ==========================================
SYSTEM_PROMPT = """Ты — добрый, терпеливый и мудрый учитель японского языка по имени Сакура-сенсей. 
Твоя задача — помочь ученику понять японский язык, используя ТОЛЬКО предоставленный контекст из учебников.

ПРАВИЛА ОТВЕТА:
1. Тон: нежный, поддерживающий, создающий атмосферу уюта — как тёплый разговор за чашкой кофе в тихом кафе. Обращайся к ученику тепло, используй слова поддержки.
2. Язык ответа: тот же, на котором задан вопрос (русский или японский). Если вопрос смешанный — отвечай на русском с японскими примерами.
3. Структура ответа:
   - Начни с тёплого приветствия или ободрения
   - Дай чёткое объяснение на основе контекста
   - Приведи 1-2 примера из учебника (если есть в контексте)
   - Закончи мотивирующей фразой
4. Если в контексте нет ответа: честно скажи "В моих учебных материалах пока нет точного ответа на этот вопрос, но давай разберёмся вместе..." и НЕ выдумывай факты.
5. Форматирование: используй жирный текст для ключевых терминов, японские примеры пиши с чтением в скобках и переводом.

КОНТЕКСТ ИЗ УЧЕБНИКОВ:
{context}

ВОПРОС УЧЕНИКА:
{question}
"""

prompt_template = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "{question}")
])

# ==========================================
# 4. УПРАВЛЕНИЕ ЖИЗНЕННЫМ ЦИКЛОМ (Lifespan)
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация моделей при старте приложения."""
    logging.info("🚀 Запуск RAG-сервиса для платформы японского языка...")
    
    # 1. Подключение к Qdrant
    try:
        app.state.qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        collections = [c.name for c in app.state.qdrant.get_collections().collections]
        if COLLECTION_NAME not in collections:
            logging.warning(f"️ Коллекция '{COLLECTION_NAME}' не найдена. Сначала запустите rag_ingest.py")
        else:
            logging.info(f"✅ Подключено к Qdrant. Коллекция: {COLLECTION_NAME}")
    except Exception as e:
        logging.error(f"❌ Ошибка подключения к Qdrant: {e}")
        raise
    
    # 2. Загрузка модели эмбеддингов
    logging.info(f"📦 Загрузка модели эмбеддингов: {EMBEDDING_MODEL_NAME}")
    app.state.embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
    logging.info("✅ Модель эмбеддингов загружена")
    
    # 3. Инициализация локальной Ollama
    logging.info(f"🤖 Подключение к локальной Ollama: {OLLAMA_BASE_URL}")
    app.state.llm = ChatOllama(
        model=LLM_MODEL_NAME,
        base_url=OLLAMA_BASE_URL,
        temperature=0.3,
        num_ctx=4096,  # Размер контекстного окна
    )
    
    # Проверка доступности модели
    try:
        test_response = app.state.llm.invoke("Тест")
        logging.info(f"✅ Локальная LLM '{LLM_MODEL_NAME}' готова к работе")
    except Exception as e:
        logging.error(f"❌ Ошибка подключения к Ollama: {e}")
        logging.error(f"Убедитесь, что Ollama запущен и модель скачана: ollama pull {LLM_MODEL_NAME}")
        raise
    
    logging.info("=" * 60)
    logging.info("🎉 RAG-сервис полностью готов к работе!")
    logging.info("=" * 60)
    yield
    
    logging.info("🛑 Завершение работы сервиса...")

app = FastAPI(
    title="🌸 Japanese Learning RAG API",
    description="Интеллектуальный помощник для изучения японского языка на основе учебников",
    version="1.0.0",
    lifespan=lifespan
)

# ==========================================
# 5. RAG ЭНДПОИНТ
# ==========================================
@app.post("/api/v1/rag/query", response_model=RAGResponse, tags=["RAG"])
async def query_rag(request: RAGRequest):
    """
    Основной RAG-эндпоинт: поиск в Qdrant + генерация ответа через локальную LLM.
    """
    start_time = time.time()
    
    try:
        # ШАГ 1: Векторизация запроса пользователя
        query_embedding = app.state.embedder.encode(
            request.query,
            normalize_embeddings=True  # Важно для косинусного расстояния
        ).tolist()
        
        # ШАГ 2: Семантический поиск в Qdrant
        search_results = app.state.qdrant.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_embedding,
            limit=request.top_k,
            score_threshold=0.5  # Отсекаем нерелевантные результаты
        )
        
        if not search_results:
            # Если ничего не найдено — возвращаем ответ без контекста
            logging.warning(f"По запросу '{request.query}' ничего не найдено в базе")
            raise HTTPException(
                status_code=404,
                detail="Релевантные материалы не найдены в базе знаний. Попробуйте переформулировать вопрос."
            )
        
        # ШАГ 3: Формирование контекста из найденных чанков
        context_parts = []
        sources = []
        
        for i, result in enumerate(search_results):
            payload = result.payload
            text = payload.get("text", "")
            source = payload.get("source", "unknown")
            
            context_parts.append(f"[Источник {i+1}: {source}]\n{text}")
            
            if request.include_sources:
                sources.append(SourceMetadata(
                    source=source,
                    score=round(result.score, 3),
                    chunk_id=payload.get("chunk_id", -1)
                ))
        
        combined_context = "\n\n---\n\n".join(context_parts)
        
        # ШАГ 4: Генерация ответа через локальную LLM
        chain = prompt_template | app.state.llm | StrOutputParser()
        
        final_answer = await chain.ainvoke({
            "context": combined_context,
            "question": request.query
        })
        
        processing_time = (time.time() - start_time) * 1000
        
        return RAGResponse(
            answer=final_answer.strip(),
            sources=sources if request.include_sources else None,
            processing_time_ms=round(processing_time, 2),
            model_used=f"{LLM_MODEL_NAME} (local)"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"❌ Ошибка в RAG-пайплайне: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Внутренняя ошибка сервера: {str(e)}"
        )

# ==========================================
# 6. ВСПОМОГАТЕЛЬНЫЕ ЭНДПОИНТЫ
# ==========================================
@app.get("/health", tags=["Monitoring"])
async def health_check():
    """Проверка работоспособности сервиса."""
    try:
        collections = app.state.qdrant.get_collections().collections
        collection_exists = any(c.name == COLLECTION_NAME for c in collections)
        return {
            "status": "healthy",
            "qdrant_connected": True,
            "collection_exists": collection_exists,
            "llm_model": LLM_MODEL_NAME,
            "ollama_url": OLLAMA_BASE_URL
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.get("/api/v1/collections", tags=["Admin"])
async def list_collections():
    """Список всех коллекций в Qdrant."""
    collections = app.state.qdrant.get_collections().collections
    return {
        "collections": [
            {
                "name": c.name,
                "vectors_count": c.vectors_count,
                "points_count": c.points_count
            }
            for c in collections
        ]
    }

@app.post("/api/v1/collections/{collection_name}/clear", tags=["Admin"])
async def clear_collection(collection_name: str):
    """Очистить коллекцию (для перезагрузки данных)."""
    try:
        app.state.qdrant.delete_collection(collection_name)
        return {"status": "ok", "message": f"Коллекция '{collection_name}' удалена"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 7. ЗАПУСК
# ==========================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Автоперезагрузка при изменении кода
        log_level="info"
    )