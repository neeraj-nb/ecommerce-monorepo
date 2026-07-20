"""
Django settings for payment_service project.

For more information on this file, see
https://docs.djangoproject.com/en/4.1/topics/settings/
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('JWT_SECRET')
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG')

# Comma-separated; defaults to '*' for dev so in-cluster hostnames
# (e.g. http://product-service:8000) are accepted. Restrict via env in prod.
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'health',
    'rest_framework_simplejwt',
    'payments',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'payment_service.urls'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'payment_service.authentication.ServiceJWTAuthentication',
    ),
}

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'payment_service.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'payment'),
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASS', 'postgres'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}


# Password validation
# https://docs.djangoproject.com/en/4.1/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/4.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_ROOT = str(BASE_DIR / "staticfiles")
STATIC_URL = 'static/'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# --- Event bus (Kafka / Redpanda) ------------------------------------------
# Comma-separated list of bootstrap servers.
KAFKA_BOOTSTRAP_SERVERS = os.environ.get(
    'KAFKA_BOOTSTRAP_SERVERS', 'redpanda:9092'
).split(',')

# Event that signals an order is ready to be charged. Defaults to the inventory
# reservation; set to "order.created" to demo payment before product-service's
# inventory consumer exists.
PAYMENT_TRIGGER_TOPIC = os.environ.get('PAYMENT_TRIGGER_TOPIC', 'inventory.reserved')


# --- Payment gateway --------------------------------------------------------
# Which gateway implementation to use. Swap for a real provider (e.g. "stripe")
# by adding it in payments/gateways/ and wiring it into get_gateway().
PAYMENT_GATEWAY = os.environ.get('PAYMENT_GATEWAY', 'dummy')

# Behaviour of the placeholder DummyPaymentGateway:
#   always_success (default) | always_fail | random
PAYMENT_MODE = os.environ.get('PAYMENT_MODE', 'always_success')


def _parse_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# P(fail) when PAYMENT_MODE=random, clamped to [0, 1].
PAYMENT_FAILURE_RATE = min(max(_parse_float(os.environ.get('PAYMENT_FAILURE_RATE', '0.3'), 0.3), 0.0), 1.0)

# Optional simulated gateway latency, in seconds.
PAYMENT_DELAY_SECONDS = _parse_float(os.environ.get('PAYMENT_DELAY_SECONDS', '0'), 0.0)

# Logging: ship app logs to Logstash (see logstash_handler.py) alongside the
# usual console output. A dead/unreachable Logstash never crashes the app --
# SocketHandler.emit swallows connection errors internally.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
        'logstash': {
            'class': 'logstash_handler.LogstashTCPHandler',
            'host': os.environ.get('LOGSTASH_HOST', 'logstash'),
            'port': int(os.environ.get('LOGSTASH_PORT', 5044)),
        },
    },
    'root': {
        'handlers': ['console', 'logstash'],
        'level': 'INFO',
    },
}
