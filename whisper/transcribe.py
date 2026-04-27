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
import re
from datetime import datetime, timedelta
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
# Transcript Cleaning Functions
# ============================================================================

def normalize_repeated_chars(word: str) -> str:
    """Replace repeated characters (5+) with single char + '...'"""
    return re.sub(r"(.)\1{4,}", r"\1...", word)


def collapse_repeated_words(words: list) -> list:
    """Collapse consecutive repeated words, keeping max 2 occurrences"""
    result = []
    prev = None
    count = 0

    for w in words:
        if w == prev:
            count += 1
        else:
            count = 1
            prev = w

        if count <= 2:
            result.append(w)

    return result


def is_noise_block(words: list) -> bool:
    """Check if a block of words is likely noise (too few unique words)"""
    if len(words) < 10:
        return False

    unique = set(words)

    # If very few unique words → this is noise
    if len(unique) <= max(2, len(words) * 0.1):
        return True

    return False


def clean_transcript(text: str) -> str:
    """
    Clean transcript text by removing:
    - Technical garbage (e.g., subtitle creator credits)
    - Repeated characters (аааааа → а...)
    - Noise blocks (blocks with very few unique words)
    - Consecutive repeated words (more than 2)
    
    Also formats output with proper sentence structure.
    """
    if not text:
        return text
    
    # 1. Remove technical garbage
    text = re.sub(r"Субтитры создавал DimaTorzok", "", text, flags=re.IGNORECASE)

    words = text.split()

    cleaned = []
    buffer = []

    for w in words:
        w = normalize_repeated_chars(w)

        # Skip words that are just repeated characters like "аааааа"
        if re.fullmatch(r"(.)\1{4,}", w):
            continue

        buffer.append(w)

        if len(buffer) >= 30:
            if not is_noise_block(buffer):
                buffer = collapse_repeated_words(buffer)
                cleaned.extend(buffer)
            buffer = []

    # Process remaining buffer
    if buffer:
        if not is_noise_block(buffer):
            buffer = collapse_repeated_words(buffer)
            cleaned.extend(buffer)

    text = " ".join(cleaned)

    # Add structure: sentence endings
    text = re.sub(r"([.!?])\s+", r"\1\n", text)

    # Clean up whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


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
                        SELECT id, title, transcribe_status, duration, text
                        FROM media
                        WHERE type = 'audio' AND language = %s
                        ORDER BY occurrence_date DESC
                    """, (language,))
                else:
                    cur.execute("""
                        SELECT id, title, transcribe_status, duration, text
                        FROM media
                        WHERE type = 'audio'
                        ORDER BY occurrence_date DESC
                    """)
                return [dict(row) for row in cur.fetchall()]

    def get_transcribe_progress_data(self, language: Optional[str] = None) -> dict:
        """Отримати дані для розрахунку прогресу транскрипції"""
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
                          AND (text IS NULL OR text = '')
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
                          AND (text IS NULL OR text = '')
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
                        result[status]['count'] = row['count']
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

    def save_draft(self, media_id: int, draft: str, status: str):
        """Зберегти чернетку транскрипції (застарілий метод для сумісності)"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE media SET draft = %s, transcribe_status = %s WHERE id = %s",
                    (draft, status, media_id)
                )
                conn.commit()

    def save_transcription(self, media_id: int, transcription: dict, status: str):
        """Зберегти транскрипцію у всіх форматах"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE media 
                       SET transcribe_txt = %s, 
                           transcribe_lrc = %s, 
                           transcribe_srt = %s, 
                           transcribe_status = %s 
                       WHERE id = %s""",
                    (transcription.get('txt'), 
                     transcription.get('lrc'), 
                     transcription.get('srt'), 
                     status, 
                     media_id)
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
    def transcribe(self, audio_path: str, language: str = 'ru') -> dict:
        """
        Транскрибувати аудіо файл.
        
        Args:
            audio_path: шлях до аудіо файлу
            language: мова транскрипції ('ru' або 'en')
        
        Returns:
            dict з ключами:
                - 'txt': звичайний текст
                - 'lrc': формат LRC (субтитри з часом)
                - 'srt': формат SRT (субтитри)
        """
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

    def transcribe(self, audio_path: str, language: str = 'ru') -> dict:
        """
        Транскрибувати аудіо файл (OpenAI Whisper).
        Примітка: OpenAI Whisper не надає часові мітки за замовчуванням,
        тому LRC та SRT будуть порожніми.
        
        Args:
            audio_path: шлях до аудіо файлу
            language: мова транскрипції ('ru' або 'en')
        """
        result = self.model.transcribe(
            audio_path,
            language=language,
            task='transcribe',
            verbose=False
        )
        txt = result['text']
        return {
            'txt': txt,
            'lrc': '',  # OpenAI Whisper не надає часові мітки без додаткової обробки
            'srt': ''   # OpenAI Whisper не надає часові мітки без додаткової обробки
        }


class FasterWhisperEngine(TranscriptionEngine):
    """Faster-Whisper движок (CTranslate2)"""

    # Initial prompts для кращого розпізнавання санскритських термінів
    INITIAL_PROMPTS = {
        'ru': """Харе Кришна. Это устная лекция на русском языке.
        В речи присутствует большое количество санскритских имён,
        эпитетов и терминов гаудия-вайшнавской традиции.
        Присутствуют имена и названия, связанные с Кришной,
        Радхой, Враджем, преданными, ачарьями, лилами и шастрами.
        Текст передаётся дословно, без художественной обработки.
        """,
        'en': """Hare Krishna. This is an oral lecture in English.
        The speech contains many Sanskrit names,
        epithets and terms of the Gaudiya Vaishnava tradition.
        There are names and titles related to Krishna,
        Radha, Vraja, devotees, acharyas, lilas and shastras.
        The text is transmitted verbatim, without artistic processing.
        """
    }

    def __init__(self, model_name: str, device: str = 'cuda', compute_type: str = 'int8_float16'):
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

    def transcribe(self, audio_path: str, language: str = 'ru') -> dict:
        """
        Транскрибувати аудіо файл.
        
        Args:
            audio_path: шлях до аудіо файлу
            language: мова транскрипції ('ru' або 'en')
        
        Returns:
            dict з ключами:
                - 'txt': звичайний текст
                - 'lrc': формат LRC (субтитри з часом)
                - 'srt': формат SRT (субтитри)
        """
        # Визначаємо initial_prompt на основі мови
        initial_prompt = self.INITIAL_PROMPTS.get(language, self.INITIAL_PROMPTS['ru'])
        
        segments, info = self.model.transcribe(
            audio_path,
            beam_size=1,  # Greedy decoding like regular Whisper default
            temperature=0.0,  # Start with 0, will fallback if needed
            language=language,
            task='transcribe',
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,
            compression_ratio_threshold=2.4,  # Default in Whisper
            log_prob_threshold=-1.0,  # Default in Whisper
            no_speech_threshold=0.6,  # Default in Whisper
        )
        
        # Збираємо сегменти у список для багаторазового використання
        segments_list = list(segments)
        
        # Генеруємо різні формати
        txt = ''.join(segment.text for segment in segments_list)
        lrc = self._generate_lrc(segments_list)
        srt = self._generate_srt(segments_list)
        
        return {
            'txt': txt,
            'lrc': lrc,
            'srt': srt
        }

    def _generate_lrc(self, segments: list) -> str:
        """
        Генерувати LRC формат.
        Формат: [mm:ss.xx]текст
        """
        lines = []
        for segment in segments:
            start_time = segment.start
            minutes = int(start_time // 60)
            seconds = start_time % 60
            # LRC формат: [mm:ss.xx]
            time_str = f"[{minutes:02d}:{seconds:05.2f}]"
            text = segment.text.strip()
            if text:
                lines.append(f"{time_str}{text}")
        return '\n'.join(lines)

    def _generate_srt(self, segments: list) -> str:
        """
        Генерувати SRT формат.
        Формат:
        1
        00:00:00,000 --> 00:00:05,000
        текст
        """
        lines = []
        for i, segment in enumerate(segments, 1):
            start_time = segment.start
            end_time = segment.end
            
            # SRT формат часу: HH:MM:SS,mmm
            start_h = int(start_time // 3600)
            start_m = int((start_time % 3600) // 60)
            start_s = int(start_time % 60)
            start_ms = int((start_time % 1) * 1000)
            
            end_h = int(end_time // 3600)
            end_m = int((end_time % 3600) // 60)
            end_s = int(end_time % 60)
            end_ms = int((end_time % 1) * 1000)
            
            time_start = f"{start_h:02d}:{start_m:02d}:{start_s:02d},{start_ms:03d}"
            time_end = f"{end_h:02d}:{end_m:02d}:{end_s:02d},{end_ms:03d}"
            
            text = segment.text.strip()
            if text:
                lines.append(f"{i}")
                lines.append(f"{time_start} --> {time_end}")
                lines.append(text)
                lines.append("")  # Порожній рядок між блоками
        return '\n'.join(lines)


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
    root_prefix: str,
    language: str = 'ru'
):
    """Процес воркера для транскрипції"""
    
    # Створити движок в кожному процесі
    engine = EngineFactory.create(engine_type, model_name, device)
    engine.load_model()
    logger.info(f"Worker {worker_id}: Ready to process (language={language})")
    
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
            transcription = engine.transcribe(audio_path, language=language)
            
            # Apply cleaning to the transcription text
            if transcription.get('txt'):
                logger.info(f"Worker {worker_id}: Cleaning transcription for {record_id}...")
                transcription['txt'] = clean_transcript(transcription['txt'])
            
            result_queue.put((record_id, transcription, None))
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

        # Конвертуємо мову з формату БД ('RUS', 'ENG') у формат Whisper ('ru', 'en')
        whisper_lang = 'ru' if language.upper() == 'RUS' else 'en'
        
        total = len(records)
        logger.info(f"Found {total} files to transcribe with {self.workers} workers")
        logger.info(f"Engine: {self.engine_type}, Model: {self.model_name}, Device: {self.device}, Language: {whisper_lang}")

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
                    self.root_prefix,
                    whisper_lang
                )
            )
            p.start()
            processes.append(p)

        # Обробляти результати
        completed = 0
        failed = 0

        while completed + failed < total:
            record_id, transcription, error = result_queue.get()

            if error:
                logger.error(f"Error for media {record_id}: {error}")
                self.db.update_status(record_id, None)
                failed += 1
            else:
                self.db.update_status(record_id, TranscribeStatus.STARTED_TRANSCRIBE.value)
                self.db.save_transcription(record_id, transcription, TranscribeStatus.FINISHED_TRANSCRIBE.value)
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

    # Розрахунок тривалості
    def get_duration_seconds(duration_val) -> float:
        """Конвертувати duration в секунди"""
        if duration_val is None:
            return 0.0
        # PostgreSQL interval повертається як timedelta
        if hasattr(duration_val, 'total_seconds'):
            return duration_val.total_seconds()
        # Якщо це рядок у форматі HH:MM:SS або подібному
        if isinstance(duration_val, str):
            parts = duration_val.split(':')
            if len(parts) == 3:
                try:
                    hours, minutes, seconds = map(float, parts)
                    return hours * 3600 + minutes * 60 + seconds
                except ValueError:
                    pass
        return 0.0

    def format_duration(seconds: float) -> str:
        """Форматувати секунди у H:MM:SS"""
        if seconds <= 0:
            return "0:00:00"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"

    # Загальна тривалість всіх аудіо
    total_duration = sum(get_duration_seconds(r['duration']) for r in records)
    
    # Тривалість транскрибованих (finished_transcribe)
    transcribed_duration = sum(
        get_duration_seconds(r['duration']) 
        for r in records 
        if r['transcribe_status'] == 'finished_transcribe'
    )
    
    # Лекції без text (потребують транскрипції)
    records_without_text = [r for r in records if not r['text']]
    without_text_count = len(records_without_text)
    without_text_duration = sum(get_duration_seconds(r['duration']) for r in records_without_text)
    
    # Транскрибовані з тих, що без text
    transcribed_without_text = [
        r for r in records_without_text 
        if r['transcribe_status'] == 'finished_transcribe'
    ]
    transcribed_without_text_duration = sum(
        get_duration_seconds(r['duration']) for r in transcribed_without_text
    )

    # Відсотки
    percent_by_count = (finished / total * 100) if total > 0 else 0
    percent_by_duration = (transcribed_duration / total_duration * 100) if total_duration > 0 else 0
    percent_without_text = (transcribed_without_text_duration / without_text_duration * 100) if without_text_duration > 0 else 0

    print("\n" + "=" * 80)
    print("TRANSCRIPTION STATUS SUMMARY")
    print("=" * 80)
    print(f"\nTotal audio files: {total}")
    print(f"Total duration: {format_duration(total_duration)}")
    print()
    print(f"Finished: {finished} ({percent_by_count:.1f}% by count)")
    print(f"Finished duration: {format_duration(transcribed_duration)} ({percent_by_duration:.1f}% by duration)")
    print(f"In progress: {in_progress}")
    print(f"Pending: {pending}")
    print(f"Remaining: {pending + in_progress}")
    print()
    print("-" * 80)
    print(f"Lectures without text: {without_text_count}")
    print(f"Duration without text: {format_duration(without_text_duration)}")
    print(f"Transcribed (of those without text): {len(transcribed_without_text)}")
    print(f"Transcribed duration (of those without text): {format_duration(transcribed_without_text_duration)} ({percent_without_text:.1f}%)")
    print("=" * 80)

    for status, items in sorted(status_counts.items()):
        print(f"\n{status.upper()}: {len(items)}")
        print("-" * 40)
        for record in items[:10]:
            duration_str = format_duration(get_duration_seconds(record['duration']))
            print(f"  [{record['id']}] ({duration_str}) {record['title'][:50]}...")
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


def cmd_progress(args):
    """Показати прогрес транскрипції з ETA"""
    from datetime import datetime as dt
    
    db = Database()
    
    # Парсимо start_time
    start_time_str = args.start_time
    try:
        # Формат: "2026-03-12 09:31:18"
        start_time = dt.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        try:
            # Альтернативний формат без секунд
            start_time = dt.strptime(start_time_str, '%Y-%m-%d %H:%M')
        except ValueError:
            print(f"Error: Invalid start_time format. Use 'YYYY-MM-DD HH:MM:SS'")
            return
    
    current_time = dt.now()
    elapsed_seconds = (current_time - start_time).total_seconds()
    
    if elapsed_seconds <= 0:
        print(f"Error: start_time is in the future")
        return
    
    # Отримуємо дані для вказаної мови або для всіх
    languages = [args.lang] if args.lang else ['RUS', 'ENG']
    
    def format_duration(seconds: float) -> str:
        """Форматувати секунди у H:MM:SS"""
        if seconds <= 0:
            return "0:00:00"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"
    
    def format_eta(seconds: float) -> str:
        """Форматувати ETA"""
        if seconds <= 0:
            return "N/A"
        if seconds > 86400:  # більше доби
            days = int(seconds // 86400)
            remaining = seconds % 86400
            hours = int(remaining // 3600)
            return f"{days}d {hours}h"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
    
    print("\n" + "=" * 80)
    print("TRANSCRIPTION PROGRESS")
    print("=" * 80)
    print(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Elapsed: {format_duration(elapsed_seconds)}")
    print("=" * 80)
    
    for lang in languages:
        data = db.get_transcribe_progress_data(lang)
        
        # Розрахунок загальних значень
        total_count = sum(s['count'] for s in data.values())
        total_duration = sum(s['duration'] for s in data.values())
        
        finished_count = data['finished_transcribe']['count']
        finished_duration = data['finished_transcribe']['duration']
        
        in_progress_count = data['started_transcribe']['count']
        in_progress_duration = data['started_transcribe']['duration']
        
        pending_count = data['pending']['count']
        pending_duration = data['pending']['duration']
        
        # Відсотки
        percent_by_count = (finished_count / total_count * 100) if total_count > 0 else 0
        percent_by_duration = (finished_duration / total_duration * 100) if total_duration > 0 else 0
        
        # Швидкість транскрипції (x)
        # x = audio_duration / real_time
        if elapsed_seconds > 0 and finished_duration > 0:
            speed_x = finished_duration / elapsed_seconds
        else:
            speed_x = 0
        
        # ETA
        remaining_duration = pending_duration + in_progress_duration
        if speed_x > 0:
            eta_seconds = remaining_duration / speed_x
        else:
            eta_seconds = 0
        
        print(f"\n--- {lang} ---")
        print(f"Total files: {total_count}")
        print(f"Total duration: {format_duration(total_duration)}")
        print()
        print(f"Finished: {finished_count} ({percent_by_count:.1f}% by count)")
        print(f"Finished duration: {format_duration(finished_duration)} ({percent_by_duration:.1f}% by duration)")
        print(f"In progress: {in_progress_count} ({format_duration(in_progress_duration)})")
        print(f"Pending: {pending_count} ({format_duration(pending_duration)})")
        print()
        print(f"Speed: {speed_x:.1f}x")
        print(f"ETA: {format_eta(eta_seconds)}")
        
        if eta_seconds > 0:
            estimated_end = current_time + timedelta(seconds=eta_seconds)
            print(f"Estimated finish: {estimated_end.strftime('%Y-%m-%d %H:%M')}")
    
    print("\n" + "=" * 80)


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
    python transcribe.py progress --start-time="2026-03-12 09:31:18" --lang=RUS
    python transcribe.py progress --start-time="2026-03-12 09:31:18"
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
    run_parser.add_argument('--model', help='Model name (e.g., medium, large-v3-turbo)')
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

    # progress command
    progress_parser = subparsers.add_parser('progress', help='Show transcription progress with ETA')
    progress_parser.add_argument('--start-time', required=True, 
                                  help='Start time in format "YYYY-MM-DD HH:MM:SS"')
    progress_parser.add_argument('--lang', default=None, 
                                  help='Language filter (default: show all languages)')
    progress_parser.set_defaults(func=cmd_progress)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
