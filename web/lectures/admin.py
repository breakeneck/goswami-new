"""
Admin configuration for lectures app.
"""
from django.contrib import admin
from .models import Category, Location, Tag, Media, MediaTag


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']
    search_fields = ['name']


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']
    search_fields = ['name']


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']
    search_fields = ['name']


class MediaTagInline(admin.TabularInline):
    model = MediaTag
    extra = 1
    autocomplete_fields = ['tag']


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'type', 'title', 'occurrence_date', 
        'location', 'visible', 'language'
    ]
    list_filter = ['type', 'visible', 'language', 'category', 'location']
    search_fields = ['title', 'teaser', 'text']
    date_hierarchy = 'occurrence_date'
    list_editable = ['visible']
    inlines = [MediaTagInline]
    
    fieldsets = (
        ('Основна інформація', {
            'fields': ('type', 'title', 'teaser', 'text')
        }),
        ('Дати', {
            'fields': ('occurrence_date', 'issue_date')
        }),
        ('Категоризація', {
            'fields': ('category', 'location', 'language')
        }),
        ('Файли', {
            'fields': ('img_url', 'file_url', 'cover_url', 'alias_url')
        }),
        ('Додатково', {
            'fields': ('duration', 'size', 'visible', 'jira_ref')
        }),
    )
