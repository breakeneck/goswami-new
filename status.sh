#!/bin/bash
# Перегляд статусу та прогресу транскрипції
# Використання: ./status.sh [status|progress] [--lang=LANG] [--start-time="YYYY-MM-DD HH:MM:SS"]
#
# Приклади:
#   ./status.sh status                    - загальний статус для всіх мов
#   ./status.sh status --lang=RUS         - статус для російських лекцій
#   ./status.sh progress --start-time="2026-03-12 09:31:18"        - прогрес для всіх мов
#   ./status.sh progress --lang=RUS --start-time="2026-03-12 09:31:18" - прогрес для RUS

cd whisper
source venv/bin/activate

COMMAND=${1:-status}
shift 2>/dev/null || true

python3 transcribe.py "$COMMAND" "$@"
