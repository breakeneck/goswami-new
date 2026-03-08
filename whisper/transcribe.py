#!/usr/bin/env python3
"""
Whisper Transcriber CLI
Транскрипція аудіо лекцій з використанням OpenAI Whisper.

Використання:
    python transcribe.py list [--lang=rus]           # Показати список файлів для транскрипції
    python transcribe.py run [--lang=rus] [--workers=4]  # Запустити транскрипцію
    python transcribe.py status                      # Показати статус всіх записів
    python transcribe.py reset <media_id>            # Скинути статус запису
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path
from multiprocessing import Process, Queue, Value, Manager
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum
import ctypes

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import torch

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TranscribeStatus(Enum):
    """Статуси транскрипції"""
    NULL = None
    STARTED_TRANSCRIBE = 'started_transcribe'
    FINISHED_TRANSCRIBE = 'finished_transcribe'
    STARTED_FORMATTING = 'started_formatting'
    FINISHED_FORMATTING = 'finished_formatting'


@dataclass
class MediaRecord:
    """Запис медіа для транскрипції"""
    id: int
    title: str
    file_url: str
    occurrence_date: datetime
    language: str
    transcribe_status: Optional[str]
    draft: Optional[str]
    text: Optional[str]

    @property
    def year_folder(self) -> str:
        """Рік з дати події"""
        return str(self.occurrence_date.year)

    @property
    def month_folder(self) -> str:
        """Місяць з дати події (2 цифри)"""
        return f"{self.occurrence_date.month:02d}"


def get_db_connection():
    """Створити нове з'єднання з БД"""
    return psycopg2.connect(
        dbname=os.getenv('DB_NAME', 'goswami.ru'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'postgres'),
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5431'),
    )


def get_media_for_transcribe(language: str = 'RUS') -> List[dict]:
    """Отримати список медіа для транскрипції"""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, title, file_url, occurrence_date, language, 
                       transcribe_status, draft, text
                FROM media
                WHERE type = 'audio'
                  AND language = %s
                  AND file_url IS NOT NULL
                  AND file_url != ''
                  AND (text IS NULL OR text = '')
                  AND transcribe_status IS NULL
                ORDER BY occurrence_date DESC
            """, (language,))
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def update_status(media_id: int, status: Optional[str]):
    """Оновити статус транскрипції"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE media SET transcribe_status = %s WHERE id = %s
            """, (status, media_id))
            conn.commit()
    finally:
        conn.close()


def save_draft(media_id: int, draft: str, status: str):
    """Зберегти чернетку транскрипції"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE media SET draft = %s, transcribe_status = %s WHERE id = %s
            """, (draft, status, media_id))
            conn.commit()
    finally:
        conn.close()


def worker_process(worker_id: int, task_queue, result_queue, model_name: str, device: str, root_prefix: str):
    """Процес воркера для транскрипції"""
    import whisper
    
    # Завантажити модель в кожному процесі
    logger.info(f"Worker {worker_id}: Loading model '{model_name}' on {device}...")
    model = whisper.load_model(model_name, device=device)
    logger.info(f"Worker {worker_id}: Model loaded")
    
    while True:
        task = task_queue.get()
        if task is None:  # Poison pill
            break
        
        record_id, title, file_url, year_folder, month_folder = task
        
        # Формуємо шлях до файлу
        audio_path = os.path.join(root_prefix, year_folder, month_folder, file_url)
        
        if not os.path.exists(audio_path):
            result_queue.put((record_id, None, f"File not found: {audio_path}"))
            continue
        
        try:
            logger.info(f"Worker {worker_id}: Transcribing {record_id} - {title[:40]}...")
            
            result = model.transcribe(
                audio_path,
                language='ru',
                task='transcribe',
                verbose=False
            )
            
            draft = result['text']
            result_queue.put((record_id, draft, None))
            logger.info(f"Worker {worker_id}: Finished {record_id}")
            
        except Exception as e:
            result_queue.put((record_id, None, str(e)))
    
    logger.info(f"Worker {worker_id}: Stopped")


def run_parallel_transcribe(language: str = 'RUS', workers: int = 4):
    """Запустити паралельну транскрипцію"""
    root_prefix = os.path.expanduser(os.getenv('MEDIA_ROOT_PREFIX', '~/hdd/media/bvgm.su'))
    model_name = os.getenv('WHISPER_MODEL', 'medium')
    device = os.getenv('WHISPER_DEVICE', 'cuda')
    
    # Перевірити GPU
    if device == 'cuda' and not torch.cuda.is_available():
        logger.warning("CUDA not available, falling back to CPU")
        device = 'cpu'
    
    # Отримати записи для обробки
    records = get_media_for_transcribe(language)
    
    if not records:
        logger.info("No media files found for transcription")
        return
    
    total = len(records)
    logger.info(f"Found {total} files to transcribe with {workers} workers")
    
    # Створити черги
    manager = Manager()
    task_queue = manager.Queue()
    result_queue = manager.Queue()
    
    # Заповнити чергу завдань
    for record in records:
        year_folder = str(record['occurrence_date'].year)
        month_folder = f"{record['occurrence_date'].month:02d}"
        task_queue.put((
            record['id'],
            record['title'],
            record['file_url'],
            year_folder,
            month_folder
        ))
    
    # Додати poison pills для кожного воркера
    for _ in range(workers):
        task_queue.put(None)
    
    # Запустити воркерів
    processes = []
    for i in range(workers):
        p = Process(
            target=worker_process,
            args=(i, task_queue, result_queue, model_name, device, root_prefix)
        )
        p.start()
        processes.append(p)
    
    # Обробляти результати
    completed = 0
    failed = 0
    
    while completed + failed < total:
        record_id, draft, error = result_queue.get()
        
        if error:
            logger.error(f"Error for media {record_id}: {error}")
            update_status(record_id, None)
            failed += 1
        else:
            # Встановити статус "почато" перед збереженням
            update_status(record_id, TranscribeStatus.STARTED_TRANSCRIBE.value)
            save_draft(record_id, draft, TranscribeStatus.FINISHED_TRANSCRIBE.value)
            completed += 1
        
        logger.info(f"Progress: {completed + failed}/{total} ({completed} ok, {failed} failed)")
    
    # Дочекатися завершення всіх процесів
    for p in processes:
        p.join()
    
    logger.info(f"Transcription completed: {completed} successful, {failed} failed")


def cmd_list(args):
    """Показати список файлів для транскрипції"""
    records = get_media_for_transcribe(args.lang)
    
    if not records:
        print(f"\nNo files found for transcription (lang={args.lang})")
        return

    print(f"\nFiles for transcription (lang={args.lang}): {len(records)}")
    print("-" * 80)
    
    for record in records:
        year_folder = str(record['occurrence_date'].year)
        month_folder = f"{record['occurrence_date'].month:02d}"
        print(f"ID: {record['id']}")
        print(f"Title: {record['title']}")
        print(f"Date: {record['occurrence_date']}")
        print(f"File: {year_folder}/{month_folder}/{record['file_url']}")
        print("-" * 80)


def cmd_run(args):
    """Запустити транскрипцію"""
    workers = args.workers or int(os.getenv('WHISPER_THREADS', '4'))
    run_parallel_transcribe(language=args.lang, workers=workers)


def cmd_status(args):
    """Показати статус всіх записів"""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if args.lang:
                cur.execute("""
                    SELECT id, title, transcribe_status
                    FROM media
                    WHERE type = 'audio' AND language = %s
                    ORDER BY occurrence_date DESC
                """, (args.lang,))
            else:
                cur.execute("""
                    SELECT id, title, transcribe_status
                    FROM media
                    WHERE type = 'audio'
                    ORDER BY occurrence_date DESC
                """)
            records = cur.fetchall()
        
        # Групування за статусом
        status_counts = {}
        for record in records:
            status = record['transcribe_status'] or 'pending'
            if status not in status_counts:
                status_counts[status] = []
            status_counts[status].append(record)

        print("\nTranscription Status Summary:")
        print("=" * 80)
        
        for status, items in sorted(status_counts.items()):
            print(f"\n{status.upper()}: {len(items)}")
            print("-" * 40)
            for record in items[:10]:
                print(f"  [{record['id']}] {record['title'][:50]}...")
            if len(items) > 10:
                print(f"  ... and {len(items) - 10} more")
            
    finally:
        conn.close()


def cmd_reset(args):
    """Скинути статус запису"""
    update_status(args.media_id, None)
    print(f"Reset status for media {args.media_id}")


def main():
    parser = argparse.ArgumentParser(
        description='Whisper Transcriber CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python transcribe.py list --lang=RUS
    python transcribe.py run --lang=RUS --workers=4
    python transcribe.py status
    python transcribe.py reset 123
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # list command
    list_parser = subparsers.add_parser('list', help='List files for transcription')
    list_parser.add_argument('--lang', default='RUS', help='Language filter (default: RUS)')
    list_parser.set_defaults(func=cmd_list)

    # run command
    run_parser = subparsers.add_parser('run', help='Run transcription')
    run_parser.add_argument('--lang', default='RUS', help='Language filter (default: RUS)')
    run_parser.add_argument('--workers', type=int, default=4, help='Number of parallel workers (default: 4)')
    run_parser.set_defaults(func=cmd_run)

    # status command
    status_parser = subparsers.add_parser('status', help='Show transcription status')
    status_parser.add_argument('--lang', default=None, help='Language filter')
    status_parser.set_defaults(func=cmd_status)

    # reset command
    reset_parser = subparsers.add_parser('reset', help='Reset media status')
    reset_parser.add_argument('media_id', type=int, help='Media ID to reset')
    reset_parser.set_defaults(func=cmd_reset)

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
