#!/usr/bin/env python3
"""
Formatter CLI - Форматування транскриптів лекцій з використанням LM Studio API.

Використання:
    python format.py run [--lang=RUS]
    python format.py list [--lang=RUS]
    python format.py status
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import requests
from time import sleep

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FormatStatus(Enum):
    """Статуси форматування"""
    NULL = None
    STARTED_TRANSCRIBE = 'started_transcribe'
    FINISHED_TRANSCRIBE = 'finished_transcribe'
    STARTED_FORMATTING = 'started_formatting'
    FINISHED_FORMATTING = 'finished_formatting'


# ============================================================================
# Database Layer
# ============================================================================

class Database:
    """Робота з базою даних PostgreSQL"""

    def __init__(self, config: dict = None):
        self.config = config or {
            'dbname': os.getenv('DB_NAME', 'goswami.ru'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'postgres'),
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5431'),
        }

    def get_connection(self):
        return psycopg2.connect(**self.config)

    def get_media_for_formatting(self, language: str = 'RUS') -> List[dict]:
        """Отримати список медіа для форматування (мають transcribe_txt, але ще не сформатовані)"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, title, file_url, occurrence_date, language, 
                           transcribe_status, draft, text, transcribe_txt, duration
                    FROM media
                    WHERE type = 'audio'
                      AND language = %s
                      AND file_url IS NOT NULL
                      AND file_url != ''
                      AND transcribe_txt IS NOT NULL
                      AND transcribe_txt != ''
                      AND (transcribe_status IS NULL 
                           OR transcribe_status = 'finished_transcribe')
                    ORDER BY occurrence_date DESC
                """, (language,))
                return [dict(row) for row in cur.fetchall()]

    def get_all_media_status(self, language: Optional[str] = None) -> List[dict]:
        """Отримати всі записи з статусом"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if language:
                    cur.execute("""
                        SELECT id, title, transcribe_status, duration, transcribe_txt
                        FROM media
                        WHERE type = 'audio' AND language = %s
                        ORDER BY occurrence_date DESC
                    """, (language,))
                else:
                    cur.execute("""
                        SELECT id, title, transcribe_status, duration, transcribe_txt
                        FROM media
                        WHERE type = 'audio'
                        ORDER BY occurrence_date DESC
                    """)
                return [dict(row) for row in cur.fetchall()]

    def get_formatting_progress_data(self, language: Optional[str] = None) -> dict:
        """Отримати дані для розрахунку прогресу форматування"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Запит для отримання статистики по статусах та тривалості
                if language:
                    cur.execute("""
                        SELECT 
                            transcribe_status,
                            COUNT(*) as count,
                            COALESCE(SUM(EXTRACT(EPOCH FROM duration)), 0) as total_duration
                        FROM media
                        WHERE type = 'audio' 
                          AND language = %s
                          AND file_url IS NOT NULL
                          AND file_url != ''
                          AND transcribe_txt IS NOT NULL
                          AND transcribe_txt != ''
                          AND (transcribe_status IS NULL OR transcribe_status = 'finished_transcribe')
                        GROUP BY transcribe_status
                    """, (language,))
                else:
                    cur.execute("""
                        SELECT 
                            transcribe_status,
                            COUNT(*) as count,
                            COALESCE(SUM(EXTRACT(EPOCH FROM duration)), 0) as total_duration
                        FROM media
                        WHERE type = 'audio'
                          AND file_url IS NOT NULL
                          AND file_url != ''
                          AND transcribe_txt IS NOT NULL
                          AND transcribe_txt != ''
                          AND (transcribe_status IS NULL OR transcribe_status = 'finished_transcribe')
                        GROUP BY transcribe_status
                    """)
                rows = cur.fetchall()
                
                result = {
                    'pending': {'count': 0, 'duration': 0.0},
                    'started_transcribe': {'count': 0, 'duration': 0.0},
                    'finished_transcribe': {'count': 0, 'duration': 0.0},
                    'started_formatting': {'count': 0, 'duration': 0.0},
                    'finished_formatting': {'count': 0, 'duration': 0.0},
                }
                
                for row in rows:
                    status = row['transcribe_status'] or 'pending'
                    if status in result:
                        result[status]['count'] = int(row['count'])
                        result[status]['duration'] = float(row['total_duration'])
                
                return result

    def update_status(self, media_id: int, status: Optional[str]):
        """Оновити статус транскрипції"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE media SET transcribe_status = %s WHERE id = %s",
                    (status, media_id)
                )
                conn.commit()

    def save_draft(self, media_id: int, draft: str):
        """Зберегти сформатований текст у поле draft"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE media SET draft = %s WHERE id = %s",
                    (draft, media_id)
                )
                conn.commit()


# ============================================================================
# LM Studio API Client
# ============================================================================

class LMApiClient:
    """Клієнт для взаємодії з LM Studio API"""

    def __init__(self):
        self.api_url = os.getenv('LM_STUDIO_API_URL', 'http://localhost:1234/v1')
        self.model = os.getenv('LM_STUDIO_MODEL', 'qwen3.5-27b-claude-4.6-os-instruct-i1')
        self.timeout = int(os.getenv('REQUEST_TIMEOUT', 300))
        self.max_retries = int(os.getenv('MAX_RETRIES', 3))
        self.temperature = float(os.getenv('TEMPERATURE', 0.3))

    def format_text(self, text: str) -> Optional[str]:
        """
        Відправити текст на форматування через LM Studio API
        
        Args:
            text: Текст для форматування
            
        Returns:
            Сформатований текст або None у разі помилки
        """
        prompt = self._create_prompt(text)
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    f"{self.api_url}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "You are a helpful assistant."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": self.temperature,
                        "stream": False
                    },
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result['choices'][0]['message']['content'].strip()
                else:
                    logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed with status {response.status_code}")
                    
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed: {e}")
            
            if attempt < self.max_retries - 1:
                sleep(5 * (attempt + 1))  # Exponential backoff
        
        return None

    def _create_prompt(self, text: str) -> str:
        """Створити промпт для форматування"""
        prompt = """Ты — профессиональный редактор текстов, специализирующийся на транскриптах лекций по восточной философии и вайшнавской традиции.

ТВОЯ ЗАДАЧА:
Исправить сырые ошибки распознавания речи (ASR) в предоставленном тексте, соблюдая следующие правила:

1. ВОССТАНОВЛЕНИЕ ТЕРМИНОВ: Самая приоритетная задача — исправить искаженные санскритские названия, имена и мантры.
- Например: "Намов Вишнухадая" -> "Намо Вишну-падая", "Гоу" -> "Гокарна", "Вайкумхи" -> "Вайкунтхи".
- Используй контекст повествования (Южная Индия, Керала, история о слоне Кешаве в Гуруваюре), чтобы узнать правильные названия.

2. СТИЛИСТИКА (Verbatim-Lite): Сохраняй живой стиль оратора. Не удаляй повторы, если они подчеркивают эмоцию, и не превращай разговорную речь в официально-деловую. Удаляй только технический мусор (например, "25 миллиметров" в начале — это ошибка таймкода).

3. ПУНКТУАЦИЯ И СТРУКТУРА:
- Разбей текст на логические абзацы.
- Используй длинное тире для пауз и прямой речи.
- Обязательно выделяй мантры отдельными блоками.

4. ЯЗЫК: Выходной текст должен быть на том же языке, что и оригинал (русский). НЕ ПЕРЕВОДИ текст, если он на русском — оставляй на русском. Термины должны быть написаны согласно общепринятой транслитерации.

ТЕКСТ ДЛЯ ОБРАБОТКИ:
[ВСТАВИТЬ ТЕКСТ ТРАНСКРИПТА ТУТ]""".replace('[ВСТАВИТЬ ТЕКСТ ТРАНСКРИПТА ТУТ]', text)
        
        return prompt


# ============================================================================
# Progress Tracking
# ============================================================================

class ProgressTracker:
    """Трекер прогресу обробки"""

    def __init__(self, total_count: int, total_duration: float):
        self.total_count = total_count
        self.total_duration = total_duration
        self.processed_count = 0
        self.processed_duration = 0.0
        self.start_time = datetime.now()

    def update(self, duration: float):
        """Оновити прогрес після обробки лекції"""
        self.processed_count += 1
        self.processed_duration += duration

    @property
    def progress_percent(self) -> float:
        """Поточний прогрес у відсотках (за кількістю лекцій)"""
        if self.total_count == 0:
            return 0.0
        return (self.processed_count / self.total_count) * 100

    @property
    def duration_progress_percent(self) -> float:
        """Поточний прогрес у відсотках (за тривалістю)"""
        if self.total_duration == 0:
            return 0.0
        return (self.processed_duration / self.total_duration) * 100

    def get_eta(self) -> timedelta:
        """Розрахувати очікуваний час завершення"""
        if self.processed_count == 0:
            return timedelta(0)
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        avg_per_lecture = elapsed / self.processed_count
        remaining = self.total_count - self.processed_count
        eta_seconds = avg_per_lecture * remaining
        
        return timedelta(seconds=eta_seconds)

    def display(self, current_title: str):
        """Відобразити поточний прогрес"""
        elapsed = datetime.now() - self.start_time
        eta = self.get_eta()
        
        print(f"\n{'='*80}")
        print(f"Прогрес: {self.processed_count}/{self.total_count} лекцій")
        print(f"Відсоток: {self.progress_percent:.1f}% (за кількістю) / {self.duration_progress_percent:.1f}% (за тривалістю)")
        print(f"Поточна лекція: {current_title}")
        print(f"Час обробки: {elapsed}")
        print(f"Залишок часу: ~{eta}")
        print(f"{'='*80}\n")


# ============================================================================
# Main Processing Logic
# ============================================================================

def process_formatting(language: str = 'RUS'):
    """Основний процес форматування"""
    db = Database()
    api_client = LMApiClient()
    
    # Отримати список медіа для обробки
    media_list = db.get_media_for_formatting(language)
    
    if not media_list:
        logger.info(f"Не знайдено лекцій для форматування (мова: {language})")
        return
    
    # Розрахувати загальну тривалість (враховуючи None значення)
    total_duration = sum(float(m['duration'].total_seconds()) for m in media_list if m['duration'])
    
    # Створити трекер прогресу
    tracker = ProgressTracker(len(media_list), total_duration)
    
    # Файл для запису помилок
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    error_file = f"errors_{timestamp}.txt"
    
    logger.info(f"Початок форматування {len(media_list)} лекцій")
    logger.info(f"Загальна тривалість: {timedelta(seconds=total_duration)}")
    
    for media in media_list:
        try:
            # Оновити статус на "started_formatting"
            db.update_status(media['id'], FormatStatus.STARTED_FORMATTING.value)
            
            text = media['transcribe_txt']
            duration = float(media['duration'].total_seconds()) if media['duration'] else 0.0
            
            logger.info(f"Форматування: {media['title']} ({duration/60:.1f} хв)")
            
            # Відправити текст на форматування
            formatted_text = api_client.format_text(text)
            
            if formatted_text is None:
                raise Exception("Не вдалося отримати відповідь від API після кількох спроб")
            
            # Зберегти результат у draft
            db.save_draft(media['id'], formatted_text)
            
            # Оновити статус на "finished_formatting"
            db.update_status(media['id'], FormatStatus.FINISHED_FORMATTING.value)
            
            # Оновити трекер прогресу
            tracker.update(duration)
            tracker.display(media['title'])
            
            logger.info(f"Успішно сформатовано: {media['title']}")
            
        except Exception as e:
            error_msg = f"{datetime.now()} - Помилка при обробці лекції ID={media['id']}, title='{media['title']}'\nПомилка: {str(e)}\n\n"
            
            with open(error_file, 'a', encoding='utf-8') as f:
                f.write(error_msg)
            
            logger.error(f"Помилка при обробці лекції ID={media['id']}: {e}")


def list_media_for_formatting(language: str = 'RUS'):
    """Відобразити список медіа для форматування"""
    db = Database()
    media_list = db.get_media_for_formatting(language)
    
    if not media_list:
        print(f"Не знайдено лекцій для форматування (мова: {language})")
        return
    
    total_duration = sum(float(m['duration'].total_seconds()) for m in media_list if m['duration'])
    
    print(f"\nЛекції для форматування ({len(media_list)} записів, всього {timedelta(seconds=total_duration)}):")
    print("-" * 80)
    
    for media in media_list:
        duration = media['duration']
        duration_str = f"{int(duration.total_seconds()/60)} хв" if duration else "N/A"
        status = media['transcribe_status'] or 'pending'
        
        print(f"ID: {media['id']}")
        print(f"  Назва: {media['title']}")
        print(f"  Дата: {media['occurrence_date']}")
        print(f"  Тривалість: {duration_str}")
        print(f"  Статус: {status}")
        print()


def show_status(language: str = 'RUS'):
    """Відобразити статус форматування"""
    db = Database()
    
    # Отримати статистику
    progress_data = db.get_formatting_progress_data(language)
    
    total_count = sum(p['count'] for p in progress_data.values())
    total_duration = sum(p['duration'] for p in progress_data.values())
    
    print(f"\nСтатус форматування (мова: {language})")
    print("=" * 80)
    print(f"Всього лекцій для обробки: {total_count}")
    print(f"Загальна тривалість: {timedelta(seconds=total_duration)}")
    print()
    
    for status, data in progress_data.items():
        if data['count'] > 0:
            duration = timedelta(seconds=data['duration'])
            print(f"{status}: {data['count']} лекцій ({duration})")


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Formatter CLI - Форматування транскриптів лекцій')
    
    subparsers = parser.add_subparsers(dest='command', help='Команда')
    
    # Команда run
    run_parser = subparsers.add_parser('run', help='Запустити процес форматування')
    run_parser.add_argument('--lang', default='RUS', help='Мова лекцій (RUS або ENG)')
    
    # Команда list
    list_parser = subparsers.add_parser('list', help='Відобразити список лекцій для форматування')
    list_parser.add_argument('--lang', default='RUS', help='Мова лекцій (RUS або ENG)')
    
    # Команда status
    status_parser = subparsers.add_parser('status', help='Показати статус форматування')
    status_parser.add_argument('--lang', default='RUS', help='Мова лекцій (RUS або ENG)')
    
    args = parser.parse_args()
    
    if args.command == 'run':
        process_formatting(language=args.lang)
    elif args.command == 'list':
        list_media_for_formatting(language=args.lang)
    elif args.command == 'status':
        show_status(language=args.lang)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
