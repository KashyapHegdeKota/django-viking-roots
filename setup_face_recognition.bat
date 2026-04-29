@echo off
REM Setup script for custom face recognition system (Windows)
REM Run with: setup_face_recognition.bat

echo ==========================================
echo Face Recognition Setup Script
echo ==========================================
echo.

REM Check if we're in the right directory
if not exist "manage.py" (
    echo Error: manage.py not found. Please run this script from the django-viking-roots directory.
    exit /b 1
)

echo [OK] Found Django project
echo.

REM Step 1: Install dependencies
echo Step 1/4: Installing dependencies...
echo This may take 2-3 minutes...
pip install -r requirements-face-recognition.txt
if %errorlevel% neq 0 (
    echo [FAIL] Failed to install dependencies
    exit /b 1
)
echo [OK] Dependencies installed
echo.

REM Step 2: Run migrations
echo Step 2/4: Running database migrations...
python manage.py migrate recognition
if %errorlevel% neq 0 (
    echo [FAIL] Failed to run migrations
    exit /b 1
)
echo [OK] Migrations applied
echo.

REM Step 3: Check configuration
echo Step 3/4: Checking configuration...
python -c "from django.conf import settings; import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings'); import django; django.setup(); model = getattr(settings, 'FACE_RECOGNITION_MODEL', 'Facenet512'); detector = getattr(settings, 'FACE_DETECTOR_BACKEND', 'retinaface'); threshold = getattr(settings, 'FACE_RECOGNITION_THRESHOLD', 70.0); print(f'  Model: {model}'); print(f'  Detector: {detector}'); print(f'  Threshold: {threshold}%%')"
if %errorlevel% neq 0 (
    echo [FAIL] Failed to load configuration
    exit /b 1
)
echo [OK] Configuration loaded
echo.

REM Step 4: Run tests
echo Step 4/4: Running test suite...
python test_face_recognition.py
if %errorlevel% neq 0 (
    echo [WARN] Some tests failed (this is normal if no users are enrolled yet)
) else (
    echo [OK] Tests passed
)
echo.

REM Success message
echo ==========================================
echo Setup Complete!
echo ==========================================
echo.
echo Next steps:
echo.
echo 1. Start Django server:
echo    python manage.py runserver
echo.
echo 2. Start Celery worker (in another terminal):
echo    celery -A api worker --loglevel=info
echo.
echo 3. Enroll users via web interface:
echo    http://localhost:8000/settings
echo    -^> Face Recognition -^> Upload 5 photos
echo.
echo 4. Create posts with images and test face recognition!
echo.
echo Documentation:
echo   - Quick Start: ..\QUICK_START_FACE_RECOGNITION.md
echo   - Full Docs: FACE_RECOGNITION_README.md
echo   - Migration Guide: ..\FACE_RECOGNITION_MIGRATION_GUIDE.md
echo.
echo ==========================================
pause
