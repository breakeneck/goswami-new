#!/bin/bash
# Запуск транскрипції аудіо лекцій
# Використання: ./run.sh [LANGUAGE] [THREADS]
# Приклад: ./run.sh RUS 4
#          ./run.sh ENG 2

# Параметри за замовчуванням
LANGUAGE=${1:-RUS}
THREADS=${2:-4}

# Фіксовані параметри моделі
ENGINE="faster-whisper"
MODEL="large-v3-turbo"

echo "=========================================="
echo "Whisper Transcription Job"
echo "=========================================="
echo "Language: $LANGUAGE"
echo "Threads:  $THREADS"
echo "Engine:   $ENGINE"
echo "Model:    $MODEL"
echo "=========================================="

# Запуск транскрипції
python3 transcribe.py run \
    --lang="$LANGUAGE" \
    --workers="$THREADS" \
    --engine="$ENGINE" \
    --model="$MODEL"
