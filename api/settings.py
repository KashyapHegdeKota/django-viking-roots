"""
Django settings for api project.
"""

from pathlib import Path
import dj_database_url
import os
import dotenv

dotenv.load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = [
    '127.0.0.1',
    'localhost',
    '.vercel.app',
    '.onrender.com',
    '.vikingroots.com',
    'api.vikingroots.com',
    'vikingroots.com',
    'www.vikingroots.com',
    'gimlisaga.org',
    'www.gimlisaga.org',
]

# Add your custom Render domain here when you get it
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Your New Split Architecture
    'heritage',
    'ai_interview',
    'community',
    'recognition',
    
    # Other Apps
    'form',
    'corsheaders',
    'storages',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # Must be before CommonMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]



CORS_ALLOWED_ORIGINS = [
    "https://frontend-viking-roots-ldwi.vercel.app",
    "https://frontend-viking-roots-one.vercel.app",
    "https://gimlisaga.org",
    "https://www.gimlisaga.org",
    "https://vikingroots.com",
    "https://www.vikingroots.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://([a-z0-9-]+\.)?vikingroots\.com$",
    r"^https://([a-z0-9-]+\.)?gimlisaga\.org$",
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = False  # True when DEBUG=True

CSRF_TRUSTED_ORIGINS = [
    "https://frontend-viking-roots-ldwi.vercel.app",
    "https://frontend-viking-roots-one.vercel.app",
    "https://gimlisaga.org",
    "https://api.vikingroots.com",
    "https://vikingroots.com",
    "https://www.vikingroots.com",
    "https://www.gimlisaga.org",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

ROOT_URLCONF = 'api.urls'

# Gemini API Key
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Supabase Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

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

WSGI_APPLICATION = 'api.wsgi.app'

# Database Configuration
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL"),
        conn_max_age=600,
        ssl_require=not DEBUG  # Only require SSL in production if you prefer
    )
}

# Add this to handle the RDS SSL Certificate specifically
if not DEBUG:
    DATABASES["default"]["OPTIONS"] = {
        "sslmode": "verify-full",
        "sslrootcert": os.path.join(BASE_DIR, "global-bundle.pem"),
    }

# Password validation
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
PASSWORD_RESET_TIMEOUT = int(os.getenv('PASSWORD_RESET_TIMEOUT', 60 * 60))

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Email configuration
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.sendgrid.net')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', 'apikey')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@kashyaphegde.com')
VIKING_ROOTS_SITE_URL = os.getenv('VIKING_ROOTS_SITE_URL', 'https://vikingroots.com')
VIKING_ROOTS_LOGIN_URL = os.getenv('VIKING_ROOTS_LOGIN_URL', f"{VIKING_ROOTS_SITE_URL.rstrip('/')}/login")
VIKING_ROOTS_PASSWORD_SETUP_URL = os.getenv(
    'VIKING_ROOTS_PASSWORD_SETUP_URL',
    f"{VIKING_ROOTS_SITE_URL.rstrip('/')}/reset-password",
)
WELCOME_FROM_EMAIL = os.getenv('WELCOME_FROM_EMAIL')
WELCOME_REPLY_TO_EMAIL = os.getenv('WELCOME_REPLY_TO_EMAIL')
WELCOME_LOGO_PATH = os.getenv(
    'WELCOME_LOGO_PATH',
    str(BASE_DIR.parent / 'frontend-viking-roots' / 'public' / 'img' / 'Logo-Transparent.png'),
)
WELCOME_LOGO_URL = os.getenv('WELCOME_LOGO_URL', f"{VIKING_ROOTS_SITE_URL.rstrip('/')}/img/Logo-Transparent.png")

# Session Configuration
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SAMESITE = 'None' if not DEBUG else 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 86400  # 1 day
SESSION_COOKIE_DOMAIN = os.getenv('SESSION_COOKIE_DOMAIN', '.vikingroots.com' if not DEBUG else None)

# CSRF Configuration
CSRF_COOKIE_SAMESITE = 'None' if not DEBUG else 'Lax'
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_DOMAIN = os.getenv('CSRF_COOKIE_DOMAIN', '.vikingroots.com' if not DEBUG else None)

# AWS S3 Configuration for Media Storage
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME', 'us-east-1')
AWS_REKOGNITION_COLLECTION_ID = os.getenv('AWS_REKOGNITION_COLLECTION_ID', 'viking-roots-faces')

# AWS Lambda Configuration
AWS_LAMBDA_FUNCTION_NAME = os.getenv('AWS_LAMBDA_FUNCTION_NAME', 'viking-roots-recognition')
LAMBDA_WEBHOOK_KEY = os.getenv('LAMBDA_WEBHOOK_KEY', 'your-secure-shared-secret-key')

# Custom Face Recognition Configuration (Replaces AWS Rekognition)
# Optimized for CPU-only deployment (AWS EC2 without GPU)
# Model options: Facenet (128-dim, fastest), Facenet512, ArcFace, VGG-Face, OpenFace, Dlib
FACE_RECOGNITION_MODEL = os.getenv('FACE_RECOGNITION_MODEL', 'Facenet')  # Facenet is faster on CPU
# Detector options: mtcnn (fast on CPU), opencv (fastest), retinaface (accurate but slower), ssd, dlib
FACE_DETECTOR_BACKEND = os.getenv('FACE_DETECTOR_BACKEND', 'mtcnn')  # MTCNN is faster on CPU than RetinaFace
# Similarity threshold (0-100, higher = stricter matching)
FACE_RECOGNITION_THRESHOLD = float(os.getenv('FACE_RECOGNITION_THRESHOLD', '70.0'))

# TensorFlow CPU optimization
import os as tf_os
tf_os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Reduce TensorFlow logging
tf_os.environ['CUDA_VISIBLE_DEVICES'] = '-1'  # Force CPU usage (no GPU)
tf_os.environ['TF_ENABLE_ONEDNN_OPTS'] = '1'  # Enable CPU optimizations

# Celery Configuration
CELERY_BROKER_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Storage configuration based on environment
if DEBUG:
    # Local development - use file system
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
    MEDIA_URL = '/media/'
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
else:
    # Production - use S3
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = 'private'
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
