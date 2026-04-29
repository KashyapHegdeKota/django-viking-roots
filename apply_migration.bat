@echo off
echo Applying database migrations...
call venv\Scripts\activate.bat
python manage.py migrate recognition
echo.
echo Migration complete!
echo.
echo Now run the test suite:
echo python test_face_recognition.py
pause
