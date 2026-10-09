from django.urls import path, include
from rest_framework.routers import DefaultRouter


from . import views

urlpatterns = [
    path('update_employees', views.upload_employee, name='update_employees'),

]