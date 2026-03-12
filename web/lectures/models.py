"""
Models for lectures app - відображають існуючу структуру бази даних.
Використовуємо managed = False оскільки таблиці вже існують.
"""
from django.db import models


class Category(models.Model):
    """Категорія медіа (тип лекції, тема)"""
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=512, verbose_name='Назва')

    class Meta:
        managed = False
        db_table = 'category'
        verbose_name = 'Категорія'
        verbose_name_plural = 'Категорії'

    def __str__(self):
        return self.name


class Location(models.Model):
    """Місце проведення лекції"""
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True, verbose_name='Назва')

    class Meta:
        managed = False
        db_table = 'location'
        verbose_name = 'Локація'
        verbose_name_plural = 'Локації'

    def __str__(self):
        return self.name


class Tag(models.Model):
    """Тег для медіа"""
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=128, unique=True, verbose_name='Назва')

    class Meta:
        managed = False
        db_table = 'tag'
        verbose_name = 'Тег'
        verbose_name_plural = 'Теги'

    def __str__(self):
        return self.name


class Media(models.Model):
    """Медіа файл (лекція, книга, стаття)"""
    MEDIA_TYPES = [
        ('audio', 'Аудіо'),
        ('book', 'Книга'),
        ('article', 'Стаття'),
    ]
    
    LANGUAGES = [
        ('RUS', 'Російська'),
        ('ENG', 'Англійська'),
    ]

    id = models.AutoField(primary_key=True)
    type = models.CharField(max_length=10, choices=MEDIA_TYPES, verbose_name='Тип')
    title = models.CharField(max_length=256, verbose_name='Назва')
    teaser = models.TextField(blank=True, null=True, verbose_name='Короткий опис')
    text = models.TextField(blank=True, null=True, verbose_name='Текст')
    occurrence_date = models.DateField(verbose_name='Дата події')
    issue_date = models.DateTimeField(blank=True, null=True, verbose_name='Дата публікації')
    category = models.ForeignKey(
        Category, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        db_column='category_id',
        verbose_name='Категорія'
    )
    location = models.ForeignKey(
        Location, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        db_column='location_id',
        verbose_name='Локація'
    )
    img_url = models.TextField(verbose_name='URL зображення')
    file_url = models.TextField(blank=True, null=True, verbose_name='URL файлу')
    cover_url = models.CharField(max_length=512, blank=True, null=True, verbose_name='URL обкладинки')
    alias_url = models.TextField(blank=True, null=True, verbose_name='Alias URL')
    visible = models.BooleanField(default=True, verbose_name='Видимий')
    duration = models.DurationField(blank=True, null=True, verbose_name='Тривалість')
    size = models.IntegerField(blank=True, null=True, verbose_name='Розмір')
    language = models.CharField(max_length=3, choices=LANGUAGES, default='RUS', verbose_name='Мова')
    jira_ref = models.CharField(max_length=128, blank=True, null=True, unique=True, verbose_name='Jira референс')
    
    # Поля для транскрипції Whisper
    draft = models.TextField(blank=True, null=True, verbose_name='Чернетка транскрипції')
    transcribe_txt = models.TextField(blank=True, null=True, verbose_name='Транскрипція (текст)')
    transcribe_lrc = models.TextField(blank=True, null=True, verbose_name='Транскрипція (LRC)')
    transcribe_srt = models.TextField(blank=True, null=True, verbose_name='Транскрипція (SRT)')
    TRANSCRIBE_STATUS_CHOICES = [
        (None, 'Очікує'),
        ('started_transcribe', 'Почато транскрипцію'),
        ('finished_transcribe', 'Завершено транскрипцію'),
        ('started_formatting', 'Почато форматування'),
        ('finished_formatting', 'Завершено форматування'),
    ]
    transcribe_status = models.CharField(
        max_length=32, 
        blank=True, 
        null=True,
        choices=TRANSCRIBE_STATUS_CHOICES,
        verbose_name='Статус транскрипції'
    )

    # Many-to-many через проміжну таблицю
    tags = models.ManyToManyField(
        Tag,
        through='MediaTag',
        related_name='media',
        verbose_name='Теги'
    )

    class Meta:
        managed = False
        db_table = 'media'
        verbose_name = 'Медіа'
        verbose_name_plural = 'Медіа'
        ordering = ['-occurrence_date']

    def __str__(self):
        return self.title

    @property
    def duration_formatted(self):
        """Форматована тривалість у вигляді H:MM:SS"""
        if not self.duration:
            return ''
        total_seconds = int(self.duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
    
    @property
    def text_html(self):
        """Конвертує Editor.js JSON формат в HTML"""
        import json
        if not self.text:
            return ''
        try:
            data = json.loads(self.text)
            if isinstance(data, str):
                return data
            if not isinstance(data, dict) or 'blocks' not in data:
                return self.text
            
            html_parts = []
            for block in data.get('blocks', []):
                block_type = block.get('type', '')
                content = block.get('data', {})
                
                if block_type == 'paragraph':
                    text = content.get('text', '')
                    if text:
                        html_parts.append(f'<p>{text}</p>')
                elif block_type == 'header':
                    level = content.get('level', 2)
                    text = content.get('text', '')
                    if text:
                        html_parts.append(f'<h{level}>{text}</h{level}>')
                elif block_type == 'list':
                    items = content.get('items', [])
                    style = content.get('style', 'unordered')
                    tag = 'ol' if style == 'ordered' else 'ul'
                    if items:
                        list_items = ''.join([f'<li>{item}</li>' for item in items])
                        html_parts.append(f'<{tag}>{list_items}</{tag}>')
                elif block_type == 'quote':
                    text = content.get('text', '')
                    caption = content.get('caption', '')
                    if text:
                        html_parts.append(f'<blockquote>{text}<cite>{caption}</cite></blockquote>')
            
            return '\n'.join(html_parts)
        except (json.JSONDecodeError, TypeError):
            # If it's not JSON, return as plain text with line breaks
            return self.text.replace('\n', '<br>')


class MediaTag(models.Model):
    """Проміжна таблиця для зв'язку Media і Tag"""
    media = models.ForeignKey(
        Media, 
        on_delete=models.CASCADE, 
        db_column='media_id',
        verbose_name='Медіа'
    )
    tag = models.ForeignKey(
        Tag, 
        on_delete=models.CASCADE, 
        db_column='tag_id',
        verbose_name='Тег'
    )

    class Meta:
        managed = False
        db_table = 'media_tag'
        unique_together = [('media', 'tag')]
        verbose_name = 'Тег медіа'
        verbose_name_plural = 'Теги медіа'


class MediaFts(models.Model):
    """Full-text search індекс для медіа"""
    # id є і PK і FK до media.id
    media = models.OneToOneField(
        Media,
        on_delete=models.CASCADE,
        db_column='id',
        primary_key=True,
        verbose_name='Медіа'
    )
    fts = models.TextField(verbose_name='FTS вектор')

    class Meta:
        managed = False
        db_table = 'media_fts'
        verbose_name = 'FTS індекс'
        verbose_name_plural = 'FTS індекси'
