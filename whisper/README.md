# Whisper Transcriber

Транскрипція аудіо лекцій з використанням OpenAI Whisper.

## Залежності системи

**ВАЖЛИВО:** Перед запуском необхідно встановити ffmpeg:

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg

# Fedora
sudo dnf install ffmpeg

# Arch Linux
sudo pacman -S ffmpeg

# macOS
brew install ffmpeg
```

## Швидкий старт

```bash
# 1. Перейти в директорію whisper
cd whisper

# 2. Створити віртуальне середовище
python3 -m venv venv

# 3. Активувати venv
source venv/bin/activate

# 4. Встановити залежності
pip install -r requirements.txt

# 5. Перевірити список файлів для транскрипції
python transcribe.py list --lang=RUS

# 6. Запустити транскрипцію
python transcribe.py run --lang=RUS
```

## Встановлення (детально)

```bash
cd whisper
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Налаштування

Файл `.env` вже створено з налаштуваннями за замовчуванням.

### Параметри:

- `DB_NAME` - ім'я бази даних (default: goswami.ru)
- `DB_USER` - користувач БД (default: postgres)
- `DB_PASSWORD` - пароль БД (default: postgres)
- `DB_HOST` - хост БД (default: localhost)
- `DB_PORT` - порт БД (default: 5431)
- `MEDIA_ROOT_PREFIX` - шлях до аудіо файлів (default: ~/hdd/media/bvgm.su)
- `WHISPER_MODEL` - модель Whisper (default: medium)
- `WHISPER_DEVICE` - пристрій для обробки (default: cuda)
- `WHISPER_THREADS` - кількість потоків (default: 4)

## Структура файлів

Аудіо файли повинні бути організовані так:
```
MEDIA_ROOT_PREFIX/
├── 2024/
│   ├── 01/
│   │   └── audio_file.mp3
│   ├── 02/
│   │   └── audio_file.mp3
│   └── ...
└── 2025/
    └── ...
```

Шлях формується як: `MEDIA_ROOT_PREFIX/YEAR/MONTH/file_url`

## Використання

### Показати список файлів для транскрипції

```bash
python transcribe.py list --lang=RUS
```

### Запустити транскрипцію

```bash
python transcribe.py run --lang=RUS
```

### Показати статус всіх записів

```bash
python transcribe.py status
```

### Скинути статус запису

```bash
python transcribe.py reset <media_id>
```

## Статуси транскрипції

- `NULL` - очікує транскрипцію
- `started_transcribe` - почато транскрипцію
- `finished_transcribe` - завершено транскрипцію
- `started_formatting` - почато форматування (LLM)
- `finished_formatting` - завершено форматування

## Поля в базі даних

Додані поля до таблиці `media`:

- `draft` - текст транскрипції (raw output from Whisper)
- `transcribe_status` - статус транскрипції

## Відновлення перерваної транскрипції

Якщо транскрипція була перервана:

1. Перевірте статус: `python transcribe.py status`
2. Запишіть ID записів зі статусом `started_transcribe`
3. Скиньте статус: `python transcribe.py reset <media_id>`
4. Запустіть транскрипцію знову: `python transcribe.py run`

## GPU прискорення

Для використання GPU (NVIDIA 3090):

1. Встановіть CUDA драйвери
2. Встановіть PyTorch з CUDA підтримкою
3. Встановіть `WHISPER_DEVICE=cuda` в `.env`

Перевірити доступність CUDA:

```python
import torch
print(torch.cuda.is_available())
```
