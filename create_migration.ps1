# PowerShell script to create migration with venv activated
Write-Host "Activating virtual environment..."
& .\venv\Scripts\Activate.ps1

Write-Host "Creating migrations..."
python manage.py makemigrations recognition

Write-Host "Applying migrations..."
python manage.py migrate recognition

Write-Host "Done!"
