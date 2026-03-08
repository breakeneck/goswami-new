"""
Views for lectures app.
"""
from django.views.generic import ListView, DetailView, TemplateView
from django.db.models import Q, F
from .models import Media, Tag, Category, Location


class HomeView(ListView):
    """Головна сторінка зі списком лекцій"""
    model = Media
    template_name = 'home.html'
    context_object_name = 'lectures'
    paginate_by = 20

    def get_queryset(self):
        return Media.objects.filter(
            type='audio',
            visible=True
        ).select_related('location', 'category').prefetch_related('tags')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Лекции Бхакти Вигьяны Госвами'
        context['show_sort'] = True
        context['active_menu'] = 'lectures'
        # Add filter options
        context['locations'] = Location.objects.all().order_by('name')
        context['categories'] = Category.objects.all().order_by('name')
        context['scriptures'] = []  # Placeholder for now
        return context


class SearchView(ListView):
    """Пошук лекцій з розширеними фільтрами"""
    model = Media
    template_name = 'home.html'
    context_object_name = 'lectures'
    paginate_by = 20

    def get_queryset(self):
        query = self.request.GET.get('q', '').strip()
        location_id = self.request.GET.get('location', '').strip()
        category_id = self.request.GET.get('category', '').strip()
        date_from = self.request.GET.get('date_from', '').strip()
        date_to = self.request.GET.get('date_to', '').strip()
        
        # Build base queryset
        qs = Media.objects.filter(
            type='audio',
            visible=True
        ).select_related('location', 'category').prefetch_related('tags')
        
        # Apply text search if provided
        if query:
            from django.db import connection
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT m.id FROM media m
                    JOIN media_fts fts ON m.id = fts.id
                    WHERE m.type = 'audio' 
                      AND m.visible = true
                      AND fts.fts @@ plainto_tsquery('russian', %s)
                    ORDER BY ts_rank(fts.fts, plainto_tsquery('russian', %s)) DESC
                """, [query, query])
                ids = [row[0] for row in cursor.fetchall()]
            
            if ids:
                qs = qs.filter(id__in=ids)
                # Сортуємо відповідно до порядку ids
                from django.db.models import Case, When, Value, IntegerField
                ordering = Case(*[When(id=id, then=Value(i)) for i, id in enumerate(ids)],
                              output_field=IntegerField())
                qs = qs.order_by(ordering)
            else:
                return Media.objects.filter(type='audio', visible=True)[:0]
        
        # Apply filters
        if location_id:
            qs = qs.filter(location_id=location_id)
        
        if category_id:
            qs = qs.filter(category_id=category_id)
        
        if date_from:
            qs = qs.filter(occurrence_date__gte=date_from)
        
        if date_to:
            qs = qs.filter(occurrence_date__lte=date_to)
        
        return qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Результаты поиска'
        context['search_query'] = self.request.GET.get('q', '')
        context['is_search'] = True
        context['active_menu'] = 'lectures'
        
        # Add filter options
        context['locations'] = Location.objects.all().order_by('name')
        context['categories'] = Category.objects.all().order_by('name')
        context['scriptures'] = []  # Placeholder for now
        
        # Preserve selected filters
        context['selected_location'] = self.request.GET.get('location', '')
        context['selected_category'] = self.request.GET.get('category', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        
        return context


class LectureDetailView(DetailView):
    """Детальна сторінка лекції"""
    model = Media
    template_name = 'lecture_detail.html'
    context_object_name = 'lecture'

    def get_queryset(self):
        return Media.objects.filter(
            type='audio',
            visible=True
        ).select_related('location', 'category').prefetch_related('tags')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'lectures'
        return context


class BooksView(ListView):
    """Сторінка з книгами"""
    model = Media
    template_name = 'home.html'
    context_object_name = 'lectures'
    paginate_by = 20

    def get_queryset(self):
        return Media.objects.filter(
            type='book',
            visible=True
        ).select_related('location', 'category').prefetch_related('tags')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Книги'
        context['is_books'] = True
        context['active_menu'] = 'books'
        return context


class ArticlesView(ListView):
    """Сторінка зі статтями"""
    model = Media
    template_name = 'home.html'
    context_object_name = 'lectures'
    paginate_by = 20

    def get_queryset(self):
        return Media.objects.filter(
            type='article',
            visible=True
        ).select_related('location', 'category').prefetch_related('tags')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Статьи'
        context['active_menu'] = 'articles'
        return context


# Static Pages
class AboutMaharajView(TemplateView):
    """Сторінка 'О Махарадже'"""
    template_name = 'static_page.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'О Махарадже'
        context['active_menu'] = 'about'
        context['content'] = '''
        <p>Бхакти Вигьяна Госвами — ученик Его Божественной Милости А. Ч. Бхактиведанты Свами Прабхупады, основателя Международного общества сознания Кришны (ИСККОН).</p>
        
        <h2>Биография</h2>
        <p>Махарадж родился в семье преданных Кришны и с раннего детства получил духовное воспитание. В 1980-х годах он принял духовное посвящение от Шрилы Прабхупады и посвятил свою жизнь распространению учения Бхагавад-гиты и Шримад-Бхагаватам.</p>
        
        <h2>Деятельность</h2>
        <p>Бхакти Вигьяна Госвами является одним из ведущих духовных учителей в ИСККОН. Он регулярно читает лекции по философии вайшнавизма, проводит семинары и ретриты по всему миру.</p>
        
        <h2>Учение</h2>
        <p>Основные темы лекций Махараджа:</p>
        <ul>
            <li>Бхагавад-гита как она есть</li>
            <li>Шримад-Бхагаватам</li>
            <li>Чайтанья-чаритамрита</li>
            <li>Философия сознания Кришны</li>
            <li>Отношения учителя и ученика</li>
            <li>Духовная практика в современном мире</li>
        </ul>
        '''
        return context


class DiscipleView(TemplateView):
    """Сторінка 'Ученикам'"""
    template_name = 'static_page.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Ученикам'
        context['active_menu'] = 'disciple'
        context['content'] = '''
        <p>Дорогие друзья, эта страница посвящена тем, кто хочет серьезно заниматься духовной практикой под руководством духовного учителя.</p>
        
        <h2>Как стать учеником?</h2>
        <p>Первый шаг — это регулярное слушание лекций и чтение книг. Рекомендуем начать с изучения "Бхагавад-гиты как она есть" и посещения ближайшего храма ИСККОН.</p>
        
        <h2>Четыре регулирующих принципа</h2>
        <ol>
            <li>Избегать мясоедения (включая рыбу и яйца)</li>
            <li>Избегать игорных игр</li>
            <li>Избегать употребления одурманивающих веществ (включая алкоголь, чай, кофе и сигареты)</li>
            <li>Избегать незаконной половой жизни</li>
        </ol>
        
        <h2>Шестнадцать кругов</h2>
        <p>Ежедневное chanting Харе Кришна маха-мантры на четках — неотъемлемая часть практики. Начните с одного круга и постепенно увеличивайте до шестнадцати.</p>
        
        <h2>Контакты</h2>
        <p>По вопросам духовной практики и инициации обращайтесь через форму обратной связи или в ближайший храм ИСККОН.</p>
        '''
        return context


class SupportView(TemplateView):
    """Сторінка 'Поддержать'"""
    template_name = 'static_page.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Поддержка проекта'
        context['active_menu'] = 'support'
        context['content'] = '''
        <p>Уважаемые посетители сайта! Проект goswami.ru существует благодаря добровольным пожертвованиям преданных.</p>
        
        <h2>Чем я могу помочь?</h2>
        
        <h3>1. Финансовая поддержка</h3>
        <p>Все средства идут на развитие проекта: техническое обслуживание, разработку новых функций, перевод и расшифровку лекций.</p>
        
        <h3>2. Распространение</h3>
        <p>Расскажите о сайте друзьям и знакомым. Поделитесь ссылками в социальных сетях.</p>
        
        <h3>3. Помощь в работе</h3>
        <p>Если у вас есть навыки в области:</p>
        <ul>
            <li>Программирования</li>
            <li>Дизайна</li>
            <li>Перевода</li>
            <li>Расшифровки аудио</li>
            <li>Корректорской работы</li>
        </ul>
        <p>Мы будем рады вашей помощи! Обращайтесь через контактную форму.</p>
        
        <h2>Способы пожертвования</h2>
        <p>Информация о способах перевода средств будет добавлена позже. Следите за обновлениями.</p>
        
        <blockquote>
            "Даже капля воды в пустыне может спасти жаждущего. Так и ваше малое пожертвование может помочь распространению духовного знания."
        </blockquote>
        '''
        return context


class ContactsView(TemplateView):
    """Сторінка 'Контакты'"""
    template_name = 'static_page.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Контакты'
        context['active_menu'] = 'contacts'
        context['content'] = '''
        <p>Свяжитесь с нами, если у вас есть вопросы, предложения или вы хотите помочь проекту.</p>
        
        <h2>Email</h2>
        <p>Общие вопросы: info@goswami.ru</p>
        <p>Техническая поддержка: support@goswami.ru</p>
        
        <h2>Социальные сети</h2>
        <p>Следите за обновлениями в социальных сетях:</p>
        <ul>
            <li>Telegram: @goswami_ru</li>
            <li>VK: vk.com/goswami</li>
            <li>YouTube: youtube.com/goswami</li>
        </ul>
        
        <h2>Адрес</h2>
        <p>Для писем и посылок:</p>
        <address>
            ИСККОН<br>
            ул. Примерная, д. 1<br>
            Москва, Россия
        </address>
        '''
        return context


class AboutPrabhupadaView(TemplateView):
    """Сторінка 'О Прабхупаде'"""
    template_name = 'static_page.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Его Божественная Милость А. Ч. Бхактиведанта Свами Прабхупада'
        context['active_menu'] = 'about'
        context['content'] = '''
        <p><strong>Шрила Прабхупада</strong> (1896–1977) — основатель Международного общества сознания Кришны (ИСККОН), учитель и духовный лидер, который принес учение Бхагавад-гиты и вайшнавизма на Запад.</p>
        
        <h2>Биография</h2>
        <p>Абхай Чаранаравинда Дас родился 1 сентября 1896 года в Калькутте, Индия. В 1922 году он встретил своего духовного учителя, Шрилу Бхактисиддханту Сарасвати Тхакура, который поручил ему распространять учение Господа Чайтаньи на английском языке.</p>
        
        <p>В 1965 году, в возрасте 69 лет, Шрила Прабхупада отправился в Нью-Йорк с книгами и небольшим количеством денег. За оставшиеся двенадцать лет своей жизни он:</p>
        <ul>
            <li>Основал более 100 храмов ИСККОН по всему миру</li>
            <li>Написал более 70 книг о философии вайшнавизма</li>
            <li>Направил кришнаитское движение по всему миру</li>
            <li>Получил тысячи учеников из разных стран</li>
        </ul>
        
        <h2>Книги</h2>
        <p>Основные произведения Шрилы Прабхупады:</p>
        <ul>
            <li>Бхагавад-гита как она есть</li>
            <li>Шримад-Бхагаватам (18 томов)</li>
            <li>Чайтанья-чаритамрита (9 томов)</li>
            <li>Нектар преданности</li>
            <li>Нектар наставлений</li>
            <li>Ишопанишад</li>
            <li>Нектар Веданты</li>
        </ul>
        
        <h2>Наследие</h2>
        <p>Сегодня ИСККОН является одной из крупнейших вайшнавских организаций в мире с миллионами последователей. Учение Шрилы Прабхупады продолжает вдохновлять людей на духовный путь по всему миру.</p>
        
        <blockquote>
            "Моя единственная просьба к вам — читайте мои книги."
            <cite>— Шрила Прабхупада</cite>
        </blockquote>
        '''
        return context


class MoreView(TemplateView):
    """Сторінка 'Еще...' з додатковими посиланнями"""
    template_name = 'static_page.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Еще'
        context['active_menu'] = 'more'
        context['content'] = '''
        <h2>Дополнительные разделы</h2>
        
        <h3>О проекте</h3>
        <p>Сайт goswami.ru создан с целью сохранения и распространения лекций Его Святейшества Бхакти Вигьяны Госвами.</p>
        
        <h3>Партнеры</h3>
        <ul>
            <li><a href="https://iskcon.org" target="_blank">ИСККОН</a> — Международное общество сознания Кришны</li>
            <li><a href="https://bhaktivedanta.org" target="_blank">Бхактиведанта Бук Траст</a> — издательство книг Шрилы Прабхупады</li>
        </ul>
        
        <h3>Полезные ссылки</h3>
        <ul>
            <li><a href="/about_prabhupada/">О Шриле Прабхупаде</a></li>
            <li><a href="/support/">Поддержать проект</a></li>
            <li><a href="/contacts/">Контакты</a></li>
        </ul>
        '''
        return context
