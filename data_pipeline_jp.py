"""
Data Pipeline для платформы Japanese_for_my_Life.
Читает учебники из папки Documents/, очищает японский текст и сохраняет в data/processed/.
"""

import re
import logging
import unicodedata
from pathlib import Path
import pandas as pd

# ==========================================
# 1. КОНФИГУРАЦИЯ (Используем относительные пути)
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Пути относительно местоположения этого скрипта
BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "Documents"             # Папка с вашими учебниками
PROCESSED_DIR = BASE_DIR / "data" / "processed" # Папка для очищенных данных (для DVC)

# Создаем папку processed, если её нет
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# 2. ФУНКЦИЯ ОЧИСТКИ ЯПОНСКОГО ТЕКСТА
# ==========================================
def clean_japanese_text(text: str) -> str:
    """Специализированная очистка для японских учебников."""
    if not isinstance(text, str):
        return ""
    
    # 1. Удаление Markdown-разметки, которая мешает RAG (но оставляем переносы строк)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Убираем жирный шрифт **текст**
    text = re.sub(r'\*(.*?)\*', r'\1', text)      # Убираем курсив *текст*
    text = re.sub(r'#{1,6}\s+', '', text)         # Убираем заголовки #, ##, но оставляем текст
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text) # Убираем ссылки [текст](url) -> текст
    
    # 2. Удаление фуриганы в формате "漢字(かんじ)" или "漢字【かんじ】"
    text = re.sub(r'([一-々〆〇]+)[\(\[【]([ぁ-んァ-ンー]+)[\)\]】]', r'\1', text)
    
    # 3. Unicode NFKC нормализация (КРИТИЧЕСКИ ВАЖНО)
    text = unicodedata.normalize('NFKC', text)
    
    # 4. Удаление невидимых символов и артефактов
    text = re.sub(r'[\u200b\u200c\u200d\ufeff\u3000]', ' ', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    
    # 5. Нормализация пробелов и переносов строк
    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

# ==========================================
# 3. ЧТЕНИЕ ФАЙЛОВ
# ==========================================
def read_markdown_file(file_path: Path) -> str:
    """Чтение Markdown файла с учетом кодировки UTF-8."""
    try:
        return file_path.read_text(encoding='utf-8')
    except Exception as e:
        logging.error(f"Ошибка чтения файла {file_path}: {e}")
        return ""

# ==========================================
# 4. ОСНОВНОЙ ПАЙПЛАЙН
# ==========================================
def process_textbooks():
    logging.info("="*60)
    logging.info("ЗАПУСК DATA PIPELINE (Japanese_for_my_Life)")
    logging.info("="*60)
    
    if not RAW_DIR.exists():
        logging.error(f"Папка с учебниками не найдена: {RAW_DIR}")
        return
    
    # Ищем все .md и .txt файлы
    files_to_process = list(RAW_DIR.glob("*.md")) + list(RAW_DIR.glob("*.txt"))
    
    if not files_to_process:
        logging.warning(f"Файлы .md или .txt не найдены в {RAW_DIR}")
        return
        
    logging.info(f"Найдено файлов для обработки: {len(files_to_process)}")
    
    all_records = []
    
    for file_path in files_to_process:
        logging.info(f"📖 Обработка файла: {file_path.name}")
        
        raw_text = read_markdown_file(file_path)
        if not raw_text:
            continue
            
        # Разбиваем текст на абзацы (по двойному переносу строки)
        # Это важно для RAG, чтобы чанки были семантически едиными
        paragraphs = raw_text.split('\n\n')
        
        for para in paragraphs:
            cleaned_para = clean_japanese_text(para)
            
            # Фильтруем слишком короткие абзацы (менее 15 символов) и пустые
            if len(cleaned_para) > 15:
                all_records.append({
                    "source_file": file_path.name,
                    "text": cleaned_para,
                    "text_length": len(cleaned_para)
                })
                
    # Создаем DataFrame
    df = pd.DataFrame(all_records)
    
    if df.empty:
        logging.warning("Не удалось извлечь валидный текст из файлов.")
        return
        
    logging.info(f" Всего абзацев после очистки: {len(df)}")
    
    # Сохраняем в Parquet
    output_file = PROCESSED_DIR / "textbooks_jp_cleaned.parquet"
    df.to_parquet(output_file, index=False, compression='snappy')
    
    logging.info(f"💾 Данные успешно сохранены в: {output_file}")
    logging.info("="*60)
    logging.info("✅ ПАЙПЛАЙН ЗАВЕРШЕН!")
    logging.info("Следующий шаг: dvc add data/processed/textbooks_jp_cleaned.parquet")
    logging.info("="*60)

if __name__ == "__main__":
    process_textbooks()