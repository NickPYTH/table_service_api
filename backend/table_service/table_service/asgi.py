import os

from django.core.asgi import get_asgi_application

from denormalized_column_storage.consumers import DenormalizedColumnStorageConsumer

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'table_service.settings')

# Инициализируем Django перед импортом middleware
django_application = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import path

# Импортируем middleware ПОСЛЕ инициализации Django
from api.middleware import WebSocketRemoteUserMiddleware
from api.consumers import TableUpdatesConsumer, CellUpdatesConsumer, CellLockUpdatesConsumer, DemonConsumer
from chat.consumers import ChatConsumer

application = ProtocolTypeRouter({
    "http": django_application,
    "websocket": WebSocketRemoteUserMiddleware(
        AuthMiddlewareStack(
            URLRouter([
                path("ws/update-service/", DenormalizedColumnStorageConsumer.as_asgi()),
                path("ws/table-updates", TableUpdatesConsumer.as_asgi()),
                path("ws/cell-updates/", CellUpdatesConsumer.as_asgi()),
                path("ws/cell-lock-updates/", CellLockUpdatesConsumer.as_asgi()),
                path("ws/chats/", ChatConsumer.as_asgi()),
                path("ws/demon/", DemonConsumer.as_asgi()),
            ])
        )
    ),
})
