# Whisper Transcriber

Транскрипція аудіо лекцій з використанням OpenAI Whisper або Faster-Whisper.

## Залежності системи (Ubuntu)

```bash
sudo apt update && sudo apt install -y \
    ffmpeg \
    python3-pip \
    python3-venv \
    nvidia-cuda-toolkit

# Перевірити CUDA
nvidia-smi
```

## Швидкий старт

```bash
cd whisper
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Список файлів для транскрипції
python transcribe.py list --lang=RUS

# Запустити транскрипцію (OpenAI Whisper)
python transcribe.py run --lang=RUS --workers=4

# Запустити з Faster-Whisper (швидше, менше пам'яті)
python transcribe.py run --lang=RUS --engine=faster-whisper --model=large-v3 --workers=4
```

## Движки транскрипції

### OpenAI Whisper
```bash
python transcribe.py run --engine=whisper --model=medium --workers=4
```

### Faster-Whisper (рекомендується)
```bash
# Завантажити модель
python transcribe.py download --engine=faster-whisper --model=large-v3

# Запустити
python transcribe.py run --engine=faster-whisper --model=large-v3 --workers=4
```

**Переваги Faster-Whisper:**
- Швидше (CTranslate2 оптимізація)
- Менше використання пам'яті
- Підтримка large-v3 моделі

## Моделі

| Модель | Пам'ять (Whisper) | Пам'ять (Faster-Whisper) | Швидкість |
|--------|-------------------|--------------------------|-----------|
| tiny | ~1GB | ~0.5GB | найшвидша |
| base | ~1GB | ~0.5GB | швидка |
| small | ~2GB | ~1GB | середня |
| medium | ~5GB | ~2.5GB | повільна |
| large-v3 | ~10GB | ~5GB | найповільніша, найкраща якість |

## Паралельна обробка

```bash
# 4 воркери з Faster-Whisper large-v3 (~20GB GPU)
python transcribe.py run --engine=faster-whisper --model=large-v3 --workers=4

# 2 воркери з Whisper medium (~10GB GPU)
python transcribe.py run --engine=whisper --model=medium --workers=2
```

## Команди

```bash
# Список файлів
python transcribe.py list --lang=RUS

# Запустити транскрипцію
python transcribe.py run --lang=RUS --workers=4

# Показати статус
python transcribe.py status

# Скинути статус запису
python transcribe.py reset 123

# Завантажити модель
python transcribe.py download --engine=faster-whisper --model=large-v3
```

## Налаштування (.env)

```bash
WHISPER_ENGINE=whisper        # або faster-whisper
WHISPER_MODEL=medium          # або large-v3
WHISPER_DEVICE=cuda           # або cpu
WHISPER_THREADS=4             # кількість воркерів
MEDIA_ROOT_PREFIX=~/hdd/media/bvgm.su
```

## Статуси транскрипції

- `NULL` - очікує транскрипцію
- `started_transcribe` - почато транскрипцію
- `finished_transcribe` - завершено транскрипцію
- `started_formatting` - почато форматування (LLM)
- `finished_formatting` - завершено форматування

## Відновлення перерваної транскрипції

```bash
# Перевірити статус
python transcribe.py status

# Скинути завислі записи
python transcribe.py reset <media_id>

# Запустити знову
python transcribe.py run --lang=RUS
```
