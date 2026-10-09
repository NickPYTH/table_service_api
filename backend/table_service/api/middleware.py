import time

from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from django.utils.deprecation import MiddlewareMixin

from api.models import RequestLog


class RemoteUserMiddleware(MiddlewareMixin):
    def process_request(self, request):
        pass


class WebSocketRemoteUserMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        # Ленивый импорт User, чтобы избежать AppRegistryNotReady
        from django.contrib.auth import get_user_model
        User = get_user_model()

        # 1. Извлекаем заголовки из scope (WebSocket-подключение)
        user_id = None


        # 3. Аутентифицируем пользователя
        if user_id:
            try:
                scope["user"] = await User.objects.aget(id=user_id)
            except User.DoesNotExist:
                scope["user"] = AnonymousUser()
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)


class RemoteUserMiddleware(MiddlewareMixin):
    def process_request(self, request):
        pass


class RequestLogMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.start_time = time.time()

    def process_response(self, request, response):
        start_time = getattr(request, 'start_time', None)
        if start_time:
            duration = time.time() - start_time
        else:
            duration = 0
        ip = self.get_client_ip(request)
        #if ip in ['127.0.0.1', 'localhost']:
        #    return response
        request_log = RequestLog.objects.create(
            user=request.user if request.user.id is not None else None,
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            duration=duration,
            ip=ip,
            user_agent=request.headers.get('User-Agent')
        )
        request_log.save()
        return response

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

