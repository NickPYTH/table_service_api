from pathlib import Path
import os
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

if not os.environ.get('RUNNING_IN_DOCKER'):
    dotenv_path = os.path.join(BASE_DIR, '.env')
    load_dotenv(dotenv_path)

SECRET_KEY = os.environ.get('SECRET_KEY')
DEBUG = os.environ.get('DEBUG') == 'True'
DB_HOST = os.environ.get('DB_HOST')
DB_PORT = os.environ.get('DB_PORT')
DB_NAME = os.environ.get('DB_NAME')
DB_SCHEMA = os.environ.get('DB_SCHEMA')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'test-vapp-03.sgp.ru', 'sco1-vapp-04.sgp.ru', '0.0.0.0', 'sco1-vapp-09.sgp.ru']


# Application definition

INSTALLED_APPS = [
    'channels',
    'django_apscheduler',
    'daphne',
    'table_service',
    'integration',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'django_filters',
    'tables.apps.TablesConfig',
    'corsheaders',
    'django.contrib.postgres',
    # 'api.apps.ApiConfig',
    'chat.apps.ChatConfig',
    'api',
    'denormalized_column_storage',
    'ai_assistant'
]


CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

ASGI_APPLICATION = 'table_service.asgi.application'
WSGI_APPLICATION = 'table_service.wsgi.application'  # Можно оставить для совместимости

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    'https://sco1-vapp-09.sgp.ru',
    'http://localhost:3000',
    'http://83.222.9.213:6767',
    'ws://localhost:3000',  # Добавьте WebSocket протокол
    'ws://83.222.9.213:6767',
]

CSRF_TRUSTED_ORIGINS = ['https://sco1-vapp-09.sgp.ru']

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'api.middleware.RemoteUserMiddleware',
    'api.middleware.RequestLogMiddleware',
    'corsheaders.middleware.CorsMiddleware',
]


AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'api.backends.RemoteUserBackend',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.RemoteUserAuthentication',
    ],
}

USE_X_FORWARDED_HOST = True

REMOTE_USER_HEADER = 'HTTP_REMOTE_USER'

ROOT_URLCONF = 'tables.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'OPTIONS': {
            'options': '-c search_path=' + DB_SCHEMA,
        },
        'NAME': DB_NAME,
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'ru-RU'

TIME_ZONE = 'Asia/Yekaterinburg'

USE_I18N = True

USE_TZ = False

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

STATIC_URL = '/api/static/'

STATIC_ROOT = os.path.join(os.path.join(BASE_DIR, 'staticfiles'))

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static')
]

APSCHEDULER_DATETIME_FORMAT = 'N j, Y, f:s a'
APSCHEDULER_RUN_NOW_TIMEOUT = 25

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'mail.sgp.ru'
EMAIL_PORT = 587  # Порт для TLS (может быть 465 для SSL)
EMAIL_USE_TLS = True  # Использовать TLS (для порта 587)
# EMAIL_USE_SSL = True  # Если используете порт 465, раскомментируйте эту строку и закомментируйте EMAIL_USE_TLS
EMAIL_HOST_USER = 'srv_mail_service'  # Ваш email на TimeWeb
EMAIL_HOST_PASSWORD = 'V_T@Dyq?nvVVf3gQy}vWe-9VE{?,Ke'  # Пароль от почты
DEFAULT_FROM_EMAIL = 'sirenkoniv@surgut.gazprom.ru'  # Email отправителя по умолчанию
SERVER_EMAIL = 'sirenkoniv@surgut.gazprom.ru'  # Email для ошибок сервера


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'DEBUG',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
    'loggers': {
        'api': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'apscheduler': {
            'handlers': ['console'],
            'level': 'WARNING',  # DEBUG → WARNING: убираем шум
            'propagate': False,  # ← ключевая строка
        },
    },
}