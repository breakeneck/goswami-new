#!/usr/bin/env python3
"""
Whisper Transcriber CLI
Транскрипція аудіо лекцій з використанням OpenAI Whisper або Faster-Whisper.

Використання:
    python transcribe.py list [--lang=RUS]
    python transcribe.py run [--lang=RUS] [--workers=4] [--engine=whisper] [--model=medium]
    python transcribe.py status
    python transcribe.py reset <media_id>
    python transcribe.py download --engine=faster-whisper --model=large-v3
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Protocol
from enum import Enum
import multiprocessing as mp

# Важливо: встановити spawn метод ДО будь-яких імпортів torch
mp.set_start_method('spawn', force=True)

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Enums and Data Classes
# ============================================================================

class TranscribeStatus(Enum):
    """Статуси транскрипції"""
    NULL = None
    STARTED_TRANSCRIBE = 'started_transcribe'
    FINISHED_TRANSCRIBE = 'finished_transcribe'
    STARTED_FORMATTING = 'started_formatting'
    FINISHED_FORMATTING = 'finished_formatting'


class EngineType(Enum):
    """Типи движків транскрипції"""
    WHISPER = 'whisper'
    FASTER_WHISPER = 'faster-whisper'


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
        return str(self.occurrence_date.year)

    @property
    def month_folder(self) -> str:
        return f"{self.occurrence_date.month:02d}"


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

    def get_media_for_transcribe(self, language: str = 'RUS') -> List[dict]:
        """Отримати список медіа для транскрипції"""
        with self.get_connection() as conn:
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

    def get_all_media_status(self, language: Optional[str] = None) -> List[dict]:
        """Отримати всі записи з статусом"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if language:
                    cur.execute("""
                        SELECT id, title, transcribe_status
                        FROM media
                        WHERE type = 'audio' AND language = %s
                        ORDER BY occurrence_date DESC
                    """, (language,))
                else:
                    cur.execute("""
                        SELECT id, title, transcribe_status
                        FROM media
                        WHERE type = 'audio'
                        ORDER BY occurrence_date DESC
                    """)
                return [dict(row) for row in cur.fetchall()]

    def update_status(self, media_id: int, status: Optional[str]):
        """Оновити статус транскрипції"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE media SET transcribe_status = %s WHERE id = %s",
                    (status, media_id)
                )
                conn.commit()

    def save_draft(self, media_id: int, draft: str, status: str):
        """Зберегти чернетку транскрипції"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE media SET draft = %s, transcribe_status = %s WHERE id = %s",
                    (draft, status, media_id)
                )
                conn.commit()


# ============================================================================
# Transcription Engines
# ============================================================================

class TranscriptionEngine(ABC):
    """Абстрактний клас для движків транскрипції"""

    def __init__(self, model_name: str, device: str = 'cuda'):
        self.model_name = model_name
        self.device = device
        self._model = None

    @abstractmethod
    def load_model(self):
        """Завантажити модель"""
        pass

    @abstractmethod
    def transcribe(self, audio_path: str) -> str:
        """Транскрибувати аудіо файл"""
        pass

    @property
    def model(self):
        if self._model is None:
            self._model = self.load_model()
        return self._model


class WhisperEngine(TranscriptionEngine):
    """OpenAI Whisper движок"""

    def load_model(self):
        import whisper
        logger.info(f"Loading Whisper model '{self.model_name}' on {self.device}...")
        model = whisper.load_model(self.model_name, device=self.device)
        logger.info("Whisper model loaded successfully")
        return model

    def transcribe(self, audio_path: str) -> str:
        result = self.model.transcribe(
            audio_path,
            language='ru',
            task='transcribe',
            verbose=False
        )
        return result['text']


class FasterWhisperEngine(TranscriptionEngine):
    """Faster-Whisper движок (CTranslate2)"""

    def __init__(self, model_name: str, device: str = 'cuda', compute_type: str = 'float16'):
        super().__init__(model_name, device)
        self.compute_type = compute_type

    def load_model(self):
        from faster_whisper import WhisperModel
        logger.info(f"Loading Faster-Whisper model '{self.model_name}' on {self.device}...")
        
        # Для CPU використовуємо int8
        if self.device == 'cpu':
            compute_type = 'int8'
        else:
            compute_type = self.compute_type
        
        model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=compute_type
        )
        logger.info("Faster-Whisper model loaded successfully")
        return model

    def transcribe(self, audio_path: str) -> str:
        segments, info = self.model.transcribe(
            audio_path,
            language='ru',
            task='transcribe'
        )
        # Об'єднати всі сегменти в один текст
        return ''.join(segment.text for segment in segments)


class EngineFactory:
    """Фабрика для створення движків транскрипції"""

    @staticmethod
    def create(engine_type: str, model_name: str, device: str = 'cuda') -> TranscriptionEngine:
        if engine_type == EngineType.WHISPER.value:
            return WhisperEngine(model_name, device)
        elif engine_type == EngineType.FASTER_WHISPER.value:
            return FasterWhisperEngine(model_name, device)
        else:
            raise ValueError(f"Unknown engine type: {engine_type}")


# ============================================================================
# Worker Process
# ============================================================================

def worker_process(
    worker_id: int,
    task_queue: mp.Queue,
    result_queue: mp.Queue,
    engine_type: str,
    model_name: str,
    device: str,
    root_prefix: str
):
    """Процес воркера для транскрипції"""
    
    # Створити движок в кожному процесі
    engine = EngineFactory.create(engine_type, model_name, device)
    engine.load_model()
    logger.info(f"Worker {worker_id}: Ready to process")
    
    while True:
        task = task_queue.get()
        if task is None:  # Poison pill
            break
        
        record_id, title, file_url, year_folder, month_folder = task
        audio_path = os.path.join(root_prefix, year_folder, month_folder, file_url)
        
        if not os.path.exists(audio_path):
            result_queue.put((record_id, None, f"File not found: {audio_path}"))
            continue
        
        try:
            logger.info(f"Worker {worker_id}: Transcribing {record_id} - {title[:40]}...")
            draft = engine.transcribe(audio_path)
            result_queue.put((record_id, draft, None))
            logger.info(f"Worker {worker_id}: Finished {record_id}")
        except Exception as e:
            result_queue.put((record_id, None, str(e)))
    
    logger.info(f"Worker {worker_id}: Stopped")


# ============================================================================
# Transcription Job Manager
# ============================================================================

class TranscriptionJob:
    """Керування завданнями транскрипції"""

    def __init__(
        self,
        db: Database,
        engine_type: str,
        model_name: str,
        device: str,
        root_prefix: str,
        workers: int = 4
    ):
        self.db = db
        self.engine_type = engine_type
        self.model_name = model_name
        self.device = device
        self.root_prefix = os.path.expanduser(root_prefix)
        self.workers = workers

    def run(self, language: str = 'RUS'):
        """Запустити паралельну транскрипцію"""
        records = self.db.get_media_for_transcribe(language)
        
        if not records:
            logger.info("No media files found for transcription")
            return

        total = len(records)
        logger.info(f"Found {total} files to transcribe with {self.workers} workers")
        logger.info(f"Engine: {self.engine_type}, Model: {self.model_name}, Device: {self.device}")

        # Створити черги
        task_queue = mp.Queue()
        result_queue = mp.Queue()

        # Заповнити чергу завдань
        for record in records:
            task_queue.put((
                record['id'],
                record['title'],
                record['file_url'],
                str(record['occurrence_date'].year),
                f"{record['occurrence_date'].month:02d}"
            ))

        # Додати poison pills
        for _ in range(self.workers):
            task_queue.put(None)

        # Запустити воркерів
        processes = []
        for i in range(self.workers):
            p = mp.Process(
                target=worker_process,
                args=(
                    i,
                    task_queue,
                    result_queue,
                    self.engine_type,
                    self.model_name,
                    self.device,
                    self.root_prefix
                )
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
                self.db.update_status(record_id, None)
                failed += 1
            else:
                self.db.update_status(record_id, TranscribeStatus.STARTED_TRANSCRIBE.value)
                self.db.save_draft(record_id, draft, TranscribeStatus.FINISHED_TRANSCRIBE.value)
                completed += 1

            logger.info(f"Progress: {completed + failed}/{total} ({completed} ok, {failed} failed)")

        # Дочекатися завершення
        for p in processes:
            p.join()

        logger.info(f"Transcription completed: {completed} successful, {failed} failed")


# ============================================================================
# Model Downloader
# ============================================================================

class ModelDownloader:
    """Завантажувач моделей"""

    @staticmethod
    def download(engine_type: str, model_name: str):
        """Завантажити модель"""
        if engine_type == EngineType.WHISPER.value:
            import whisper
            logger.info(f"Downloading Whisper model '{model_name}'...")
            whisper.load_model(model_name)
            logger.info("Whisper model downloaded successfully")
        
        elif engine_type == EngineType.FASTER_WHISPER.value:
            from faster_whisper import WhisperModel
            logger.info(f"Downloading Faster-Whisper model '{model_name}'...")
            WhisperModel(model_name, device='cpu', compute_type='int8')
            logger.info("Faster-Whisper model downloaded successfully")
        
        else:
            raise ValueError(f"Unknown engine type: {engine_type}")


# ============================================================================
# CLI Commands
# ============================================================================

def cmd_list(args):
    """Показати список файлів для транскрипції"""
    db = Database()
    records = db.get_media_for_transcribe(args.lang)

    if not records:
        print(f"\nNo files found for transcription (lang={args.lang})")
        return

    print(f"\nFiles for transcription (lang={args.lang}): {len(records)}")
    print("-" * 80)

    for record in records[:50]:  # Обмежити вивід
        year_folder = str(record['occurrence_date'].year)
        month_folder = f"{record['occurrence_date'].month:02d}"
        print(f"ID: {record['id']}")
        print(f"Title: {record['title']}")
        print(f"Date: {record['occurrence_date']}")
        print(f"File: {year_folder}/{month_folder}/{record['file_url']}")
        print("-" * 80)

    if len(records) > 50:
        print(f"... and {len(records) - 50} more files")


def cmd_run(args):
    """Запустити транскрипцію"""
    db = Database()
    
    engine_type = args.engine or os.getenv('WHISPER_ENGINE', 'whisper')
    model_name = args.model or os.getenv('WHISPER_MODEL', 'medium')
    device = args.device or os.getenv('WHISPER_DEVICE', 'cuda')
    workers = args.workers or int(os.getenv('WHISPER_THREADS', '4'))
    root_prefix = os.getenv('MEDIA_ROOT_PREFIX', '~/hdd/media/bvgm.su')

    # Перевірити GPU
    if device == 'cuda':
        try:
            import torch
            if not torch.cuda.is_available():
                logger.warning("CUDA not available, falling back to CPU")
                device = 'cpu'
        except ImportError:
            device = 'cpu'

    job = TranscriptionJob(
        db=db,
        engine_type=engine_type,
        model_name=model_name,
        device=device,
        root_prefix=root_prefix,
        workers=workers
    )

    job.run(language=args.lang)


def cmd_status(args):
    """Показати статус всіх записів"""
    db = Database()
    records = db.get_all_media_status(args.lang)

    # Групування за статусом
    status_counts = {}
    for record in records:
        status = record['transcribe_status'] or 'pending'
        if status not in status_counts:
            status_counts[status] = []
        status_counts[status].append(record)

    total = len(records)
    finished = len(status_counts.get('finished_transcribe', []))
    pending = len(status_counts.get('pending', []))
    in_progress = len(status_counts.get('started_transcribe', []))

    percent = (finished / total * 100) if total > 0 else 0

    print("\n" + "=" * 80)
    print("TRANSCRIPTION STATUS SUMMARY")
    print("=" * 80)
    print(f"\nTotal audio files: {total}")
    print(f"Finished: {finished} ({percent:.1f}%)")
    print(f"In progress: {in_progress}")
    print(f"Pending: {pending}")
    print(f"Remaining: {pending + in_progress}")
    print("=" * 80)

    for status, items in sorted(status_counts.items()):
        print(f"\n{status.upper()}: {len(items)}")
        print("-" * 40)
        for record in items[:10]:
            print(f"  [{record['id']}] {record['title'][:50]}...")
        if len(items) > 10:
            print(f"  ... and {len(items) - 10} more")


def cmd_reset(args):
    """Скинути статус запису"""
    db = Database()
    db.update_status(args.media_id, None)
    print(f"Reset status for media {args.media_id}")


def cmd_download(args):
    """Завантажити модель"""
    engine_type = args.engine or 'faster-whisper'
    model_name = args.model or 'large-v3'
    
    ModelDownloader.download(engine_type, model_name)


def main():
    parser = argparse.ArgumentParser(
        description='Whisper Transcriber CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python transcribe.py list --lang=RUS
    python transcribe.py run --lang=RUS --workers=4
    python transcribe.py run --lang=RUS --engine=faster-whisper --model=large-v3
    python transcribe.py status
    python transcribe.py reset 123
    python transcribe.py download --engine=faster-whisper --model=large-v3
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
    run_parser.add_argument('--workers', type=int, default=4, help='Number of parallel workers')
    run_parser.add_argument('--engine', choices=['whisper', 'faster-whisper'], help='Transcription engine')
    run_parser.add_argument('--model', help='Model name (e.g., medium, large-v3)')
    run_parser.add_argument('--device', choices=['cuda', 'cpu'], help='Device to use')
    run_parser.set_defaults(func=cmd_run)

    # status command
    status_parser = subparsers.add_parser('status', help='Show transcription status')
    status_parser.add_argument('--lang', default=None, help='Language filter')
    status_parser.set_defaults(func=cmd_status)

    # reset command
    reset_parser = subparsers.add_parser('reset', help='Reset media status')
    reset_parser.add_argument('media_id', type=int, help='Media ID to reset')
    reset_parser.set_defaults(func=cmd_reset)

    # download command
    download_parser = subparsers.add_parser('download', help='Download model')
    download_parser.add_argument('--engine', choices=['whisper', 'faster-whisper'], default='faster-whisper')
    download_parser.add_argument('--model', default='large-v3', help='Model name')
    download_parser.set_defaults(func=cmd_download)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
