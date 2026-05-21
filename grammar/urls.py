from django.urls import path

from . import views

app_name = 'grammar'

urlpatterns = [
    path('', views.topic_list, name='topic_list'),
    path('coach/', views.coach, name='coach'),
    path('personal/<slug:kind>/', views.personal_practice, name='personal_practice'),
    path('personal/<slug:kind>/<int:position>/', views.personal_question, name='personal_question'),
    path('personal/<slug:kind>/results/', views.personal_results, name='personal_results'),
    path('<slug:slug>/', views.topic_detail, name='topic_detail'),
    path('<slug:slug>/exercise/', views.exercise, name='exercise'),
    path('<slug:slug>/exercise/<int:position>/', views.exercise_question, name='exercise_question'),
    path('<slug:slug>/results/', views.exercise_results, name='exercise_results'),
]
