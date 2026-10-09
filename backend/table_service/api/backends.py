import os
import random
from datetime import date

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User

from tables.models import UserOnlineHistory


class RemoteUserBackend(ModelBackend):
    def authenticate(self, request, remote_user=None):
        if remote_user is None:
            remote_user = request.META.get('HTTP_X_REMOTE_USER')

        user = None
        if remote_user:
            try:
                user = User.objects.get(username=remote_user)
            except User.DoesNotExist:
                DEBUG = os.environ.get('DEBUG')
                if DEBUG == 'True':
                    return User.objects.get(pk=1)
                else:
                    return None
        else:
            try:
                user = User.objects.get(pk=1)
            except User.DoesNotExist:
                return None

        # Логируем вход пользователя
        if user:
            self.log_user_login(user)

        return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    def log_user_login(self, user):
        """
        Логирование входа пользователя
        Создает запись в UserOnlineHistory для текущей даты,
        если такой записи еще нет
        """
        try:
            today = date.today()

            # Проверяем, есть ли уже запись за сегодня
            existing_record = UserOnlineHistory.objects.filter(
                user=user,
                date=today
            ).first()

            if not existing_record:
                # Создаем новую запись
                UserOnlineHistory.objects.create(
                    user=user,
                    date=today
                )
                print(f"Запись о входе пользователя {user.username} создана для {today}")
            else:
                print(f"Запись о входе пользователя {user.username} уже существует для {today}")

        except Exception as e:
            # Логируем ошибку, но не прерываем аутентификацию
            print(f"Ошибка при логировании входа пользователя {user.username}: {str(e)}")