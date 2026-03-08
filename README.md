# Goswami.ru - Django версія

Сайт лекцій Бхакті Вігьяни Госвамі на Django.

## Структура проєкту

```
.
├── database/               # PostgreSQL з наявною базою даних
├── web/                    # Django додаток
│   ├── goswami/            # Налаштування Django
│   ├── lectures/           # Додаток з лекціями
│   ├── templates/          # HTML шаблони
│   ├── static/             # CSS, JS, images
│   ├── venv/               # Virtual environment (створюється локально)
│   ├── manage.py           # Django management
│   ├── requirements.txt    # Python залежності
│   ├── .env                # Локальні налаштування
│   ├── .env.example        # Приклад налаштувань
│   ├── setup_venv.sh       # Скрипт налаштування venv (Linux/Mac)
│   ├── setup_venv.ps1      # Скрипт налаштування venv (Windows)
│   ├── run_local.sh        # Запуск локально (Linux/Mac)
│   └── run_local.ps1       # Запуск локально (Windows)
├── docker-compose.yml      # Docker конфігурація
└── README.md
```

## Запуск

### Варіант 1: Docker (рекомендується)

```bash
docker compose up -d
```

- Сайт: http://localhost:8000
- Адмінка: http://localhost:8000/admin

Створити суперкористувача:
```bash
docker compose exec web python manage.py createsuperuser
```

### Варіант 2: Local development з venv

**Linux/Mac:**
```bash
cd web
./setup_venv.sh    # Перший раз - створення venv
./run_local.sh     # Запуск сервера
```

**Windows (PowerShell):**
```powershell
cd web
.\setup_venv.ps1   # Перший раз - створення venv
.\run_local.ps1    # Запуск сервера
```

**Вручну:**
```bash
cd web
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# або: venv\Scripts\activate  # Windows

pip install -r requirements.txt
python manage.py migrate --run-syncdb
python manage.py runserver
```

Створити суперкористувача локально:
```bash
./create_admin.sh      # Linux/Mac
.\create_admin.ps1     # Windows
```

## Функціонал

- **Головна сторінка** - список лекцій з сортуванням по даті
- **Пошук** - full-text search по лекціях (через PostgreSQL tsvector)
- **Книги** - окремий розділ з книгами
- **Адмінка** - керування всіма даними
- **jQuery** - інтерактивність на фронтенді

## База даних

Використовується існуюча PostgreSQL база з таблицями:
- `media` - лекції, книги, статті
- `category` - категорії
- `location` - локації
- `tag` - теги
- `media_tag` - зв'язок медіа з тегами
- `media_fts` - full-text search індекс

## Стилі

Всі стилі в одному файлі: `web/static/css/style.css`

## Технології

- Django 5.x
- PostgreSQL 16
- jQuery 3.7
- Docker & Docker Compose
