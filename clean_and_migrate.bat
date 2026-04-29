@echo off
echo Cleaning migration cache...
rmdir /s /q recognition\migrations\__pycache__ 2>nul
mkdir recognition\migrations\__pycache__
type nul > recognition\migrations\__pycache__\__init__.py

echo.
echo Applying migrations...
python manage.py migrate recognition

echo.
echo Running tests...
python test_face_recognition.py

pause
