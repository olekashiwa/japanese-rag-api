"""
RAG Ingestion Pipeline для Japanese_for_my_Life.
Загружает очищенные данные из Parquet в Qdrant.
"""
import os
import logging
import time
from pathlib import Path
import pandas as pd
from tqdm import tqdm
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, OptimizersConfigDiff
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter

# КОНФИГУРАЦИЯ
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
BASE_DIR = Path(__file__).parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = "jp_learning_materials"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64

def ingest():
    logging.info(" Запуск RAG Ingestion...")
    
    # 1. Поиск Parquet файла
    parquet_files = list(PROCESSED_DIR.glob("*_cleaned.parquet"))
    if not parquet_files:
        logging.error("❌ Очищенный Parquet файл не найден! Сначала запустите data_pipeline_jp.py")
        return
    
    parquet_path = max(parquet_files, key=lambda p: p.stat().st_mtime)
    logging.info(f"📂 Найден файл: {parquet_path.name}")
    
    # 2. Инициализация
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    model = SentenceTransformer(EMBEDDING_MODEL)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, 
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "、", " ", ""],
        length_function=len
    )
    
    # 3. Создание коллекции
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            optimizers_config=OptimizersConfigDiff(indexing_threshold=10000)
        )
        logging.info(f"✅ Коллекция '{COLLECTION_NAME}' создана")
    else:
        logging.info(f"📦 Коллекция '{COLLECTION_NAME}' уже существует")
        
    # 4. Обработка данных
    df = pd.read_parquet(parquet_path)
    text_col = next((c for c in ['text', 'sentence', 'content'] if c in df.columns), df.columns[0])
    
    all_points = []
    global_id = 0
    
    logging.info("✂️ Разбиение и векторизация...")
    for _, row in tqdm(df.iterrows(), total=len(df)):
        chunks = splitter.split_text(str(row[text_col]))
        for chunk in chunks:
            if len(chunk.strip()) < 20: continue
            
            embedding = model.encode(chunk, normalize_embeddings=True).tolist()
            all_points.append(PointStruct(
                id=global_id,
                vector=embedding,
                payload={
                    "text": chunk,
                    "source": str(row.get("source_file", parquet_path.stem)),
                    "chunk_id": global_id,
                    "language": "ja"
                }
            ))
            global_id += 1
            
            # Загрузка батчами по 64 точки
            if len(all_points) >= 64:
                client.upsert(collection_name=COLLECTION_NAME, points=all_points)
                all_points = []
                
    # Загрузка остатка
    if all_points:
        client.upsert(collection_name=COLLECTION_NAME, points=all_points)
        
    logging.info(f"🎉 Завершено! Всего загружено точек: {global_id}")

if __name__ == "__main__":
    ingest()