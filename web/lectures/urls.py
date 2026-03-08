"""
URL configuration for lectures app.
"""
from django.urls import path
from . import views

app_name = 'lectures'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('search/', views.SearchView.as_view(), name='search'),
    path('lecture/<int:pk>/', views.LectureDetailView.as_view(), name='lecture_detail'),
    path('books/', views.BooksView.as_view(), name='books'),
    path('articles/', views.ArticlesView.as_view(), name='articles'),
    
    # Static pages
    path('about_maharaj/', views.AboutMaharajView.as_view(), name='about_maharaj'),
    path('disciple/', views.DiscipleView.as_view(), name='disciple'),
    path('support/', views.SupportView.as_view(), name='support'),
    path('contacts/', views.ContactsView.as_view(), name='contacts'),
    path('about_prabhupada/', views.AboutPrabhupadaView.as_view(), name='about_prabhupada'),
    path('more/', views.MoreView.as_view(), name='more'),
]
