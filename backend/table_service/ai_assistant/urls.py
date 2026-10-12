from django.urls import path

from ai_assistant import views

urlpatterns = [
    path('process_prompt/', views.process_prompt, name='process_prompt'),
]
