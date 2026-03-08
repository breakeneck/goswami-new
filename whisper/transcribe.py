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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import whisper
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


class Database:
    """Робота з базою даних PostgreSQL"""

    def __init__(self):
        self.conn_params = {
            'dbname': os.getenv('DB_NAME', 'goswami.ru'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'postgres'),
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5431'),
        }
        self.conn = None

    def connect(self):
        """Підключення до БД"""
        self.conn = psycopg2.connect(**self.conn_params)
        return self.conn

    def close(self):
        """Закрити з'єднання"""
        if self.conn:
            self.conn.close()

    def get_media_for_transcribe(self, language: str = 'RUS') -> List[MediaRecord]:
        """Отримати список медіа для транскрипції (без тексту, без завершеного статусу)"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
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
            
            return [MediaRecord(**row) for row in cur.fetchall()]

    def get_all_media_status(self, language: Optional[str] = None) -> List[MediaRecord]:
        """Отримати всі записи з статусом"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            if language:
                cur.execute("""
                    SELECT id, title, file_url, occurrence_date, language,
                           transcribe_status, draft, text
                    FROM media
                    WHERE type = 'audio' AND language = %s
                    ORDER BY occurrence_date DESC
                """, (language,))
            else:
                cur.execute("""
                    SELECT id, title, file_url, occurrence_date, language,
                           transcribe_status, draft, text
                    FROM media
                    WHERE type = 'audio'
                    ORDER BY occurrence_date DESC
                """)
            
            return [MediaRecord(**row) for row in cur.fetchall()]

    def update_status(self, media_id: int, status: Optional[str]):
        """Оновити статус транскрипції"""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE media SET transcribe_status = %s WHERE id = %s
            """, (status, media_id))
            self.conn.commit()

    def save_draft(self, media_id: int, draft: str, status: str):
        """Зберегти чернетку транскрипції"""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE media SET draft = %s, transcribe_status = %s WHERE id = %s
            """, (draft, status, media_id))
            self.conn.commit()

    def reset_status(self, media_id: int):
        """Скинути статус запису"""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE media SET transcribe_status = NULL WHERE id = %s
            """, (media_id,))
            self.conn.commit()


class WhisperTranscriber:
    """Транскрипція з використанням Whisper"""

    def __init__(self, model_name: str = 'medium', device: str = 'cuda'):
        self.model_name = model_name
        self.device = device
        self.model = None

    def load_model(self):
        """Завантажити модель Whisper"""
        if self.model is None:
            logger.info(f"Loading Whisper model '{self.model_name}' on {self.device}...")
            self.model = whisper.load_model(self.model_name, device=self.device)
            logger.info("Model loaded successfully")
        return self.model

    def transcribe(self, audio_path: str) -> str:
        """Транскрибувати аудіо файл"""
        model = self.load_model()
        
        logger.info(f"Transcribing: {audio_path}")
        
        result = model.transcribe(
            audio_path,
            language='ru',
            task='transcribe',
            verbose=False
        )
        
        return result['text']


class TranscriptionJob:
    """Керування завданнями транскрипції"""

    def __init__(self, db: Database, transcriber: WhisperTranscriber, root_prefix: str):
        self.db = db
        self.transcriber = transcriber
        self.root_prefix = os.path.expanduser(root_prefix)

    def get_audio_path(self, record: MediaRecord) -> Optional[str]:
        """Отримати повний шлях до аудіо файлу"""
        if not record.file_url:
            return None
        
        # Шлях: root_prefix/YEAR/MONTH/file_url
        path = Path(self.root_prefix) / record.year_folder / record.month_folder / record.file_url
        
        if path.exists():
            return str(path)
        
        # Спробуємо без file_url як директорії
        alt_path = Path(self.root_prefix) / record.year_folder / record.month_folder / record.file_url
        if alt_path.exists():
            return str(alt_path)
        
        return None

    def process_record(self, record: MediaRecord) -> bool:
        """Обробити один запис"""
        try:
            # Отримати шлях до файлу
            audio_path = self.get_audio_path(record)
            if not audio_path:
                logger.error(f"File not found for media {record.id}: {record.title}")
                return False

            # Встановити статус "почато"
            self.db.update_status(record.id, TranscribeStatus.STARTED_TRANSCRIBE.value)

            # Транскрибувати
            draft = self.transcriber.transcribe(audio_path)

            # Зберегти результат
            self.db.save_draft(record.id, draft, TranscribeStatus.FINISHED_TRANSCRIBE.value)
            
            logger.info(f"Finished transcribing media {record.id}: {record.title}")
            return True

        except Exception as e:
            logger.error(f"Error transcribing media {record.id}: {e}")
            # Скинути статус при помилці, щоб можна було повторити
            self.db.update_status(record.id, None)
            return False

    def run(self, language: str = 'RUS', workers: int = 4):
        """Запустити транскрипцію з кількома потоками"""
        records = self.db.get_media_for_transcribe(language)
        
        if not records:
            logger.info("No media files found for transcription")
            return

        logger.info(f"Found {len(records)} files to transcribe")
        
        # Попередньо завантажити модель
        self.transcriber.load_model()

        # Запустити обробку в потоках
        # Примітка: Whisper GPU обробляє послідовно, але підготовка файлів може бути паралельною
        completed = 0
        failed = 0

        # Для GPU краще використовувати послідовну обробку, але з batch
        for record in records:
            logger.info(f"Processing [{completed + failed + 1}/{len(records)}]: {record.title}")
            if self.process_record(record):
                completed += 1
            else:
                failed += 1

        logger.info(f"Transcription completed: {completed} successful, {failed} failed")


def cmd_list(args):
    """Показати список файлів для транскрипції"""
    db = Database()
    db.connect()
    
    try:
        records = db.get_media_for_transcribe(args.lang)
        
        if not records:
            print(f"\nNo files found for transcription (lang={args.lang})")
            return

        print(f"\nFiles for transcription (lang={args.lang}): {len(records)}")
        print("-" * 80)
        
        for record in records:
            print(f"ID: {record.id}")
            print(f"Title: {record.title}")
            print(f"Date: {record.occurrence_date}")
            print(f"File: {record.year_folder}/{record.month_folder}/{record.file_url}")
            print("-" * 80)
            
    finally:
        db.close()


def cmd_run(args):
    """Запустити транскрипцію"""
    db = Database()
    db.connect()
    
    try:
        model_name = os.getenv('WHISPER_MODEL', 'medium')
        device = os.getenv('WHISPER_DEVICE', 'cuda')
        root_prefix = os.getenv('MEDIA_ROOT_PREFIX', '~/hdd/media/bvgm.su')
        workers = args.workers or int(os.getenv('WHISPER_THREADS', '4'))

        # Перевірити GPU
        if device == 'cuda' and not torch.cuda.is_available():
            logger.warning("CUDA not available, falling back to CPU")
            device = 'cpu'

        transcriber = WhisperTranscriber(model_name=model_name, device=device)
        job = TranscriptionJob(db, transcriber, root_prefix)
        
        job.run(language=args.lang, workers=workers)
        
    finally:
        db.close()


def cmd_status(args):
    """Показати статус всіх записів"""
    db = Database()
    db.connect()
    
    try:
        records = db.get_all_media_status(args.lang)
        
        # Групування за статусом
        status_counts = {}
        for record in records:
            status = record.transcribe_status or 'pending'
            if status not in status_counts:
                status_counts[status] = []
            status_counts[status].append(record)

        print("\nTranscription Status Summary:")
        print("=" * 80)
        
        for status, items in sorted(status_counts.items()):
            print(f"\n{status.upper()}: {len(items)}")
            print("-" * 40)
            for record in items[:10]:  # Показати перші 10
                print(f"  [{record.id}] {record.title[:50]}...")
            if len(items) > 10:
                print(f"  ... and {len(items) - 10} more")
            
    finally:
        db.close()


def cmd_reset(args):
    """Скинути статус запису"""
    db = Database()
    db.connect()
    
    try:
        db.reset_status(args.media_id)
        print(f"Reset status for media {args.media_id}")
    finally:
        db.close()


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
    run_parser.add_argument('--workers', type=int, default=4, help='Number of workers (default: 4)')
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
