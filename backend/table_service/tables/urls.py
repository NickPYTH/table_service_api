from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [

    path('ai_assistant/', include('ai_assistant.urls')),
    path('denormalized_column_storage/', include('denormalized_column_storage.urls')),
    path('api/integration/', include('integration.urls')),
    path('api/', include('api.urls')),
    path('api/admin/', admin.site.urls),

]
