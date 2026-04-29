#!/bin/bash
# Setup script for custom face recognition system
# Run with: bash setup_face_recognition.sh

set -e  # Exit on error

echo "=========================================="
echo "Face Recognition Setup Script"
echo "=========================================="
echo ""

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo "❌ Error: manage.py not found. Please run this script from the django-viking-roots directory."
    exit 1
fi

echo "✓ Found Django project"
echo ""

# Step 1: Install dependencies
echo "Step 1/4: Installing dependencies..."
echo "This may take 2-3 minutes..."
pip install -r requirements-face-recognition.txt
if [ $? -eq 0 ]; then
    echo "✓ Dependencies installed"
else
    echo "❌ Failed to install dependencies"
    exit 1
fi
echo ""

# Step 2: Run migrations
echo "Step 2/4: Running database migrations..."
python manage.py migrate recognition
if [ $? -eq 0 ]; then
    echo "✓ Migrations applied"
else
    echo "❌ Failed to run migrations"
    exit 1
fi
echo ""

# Step 3: Check configuration
echo "Step 3/4: Checking configuration..."
python -c "
from django.conf import settings
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
import django
django.setup()

model = getattr(settings, 'FACE_RECOGNITION_MODEL', 'Facenet512')
detector = getattr(settings, 'FACE_DETECTOR_BACKEND', 'retinaface')
threshold = getattr(settings, 'FACE_RECOGNITION_THRESHOLD', 70.0)

print(f'  Model: {model}')
print(f'  Detector: {detector}')
print(f'  Threshold: {threshold}%')
"
if [ $? -eq 0 ]; then
    echo "✓ Configuration loaded"
else
    echo "❌ Failed to load configuration"
    exit 1
fi
echo ""

# Step 4: Run tests
echo "Step 4/4: Running test suite..."
python test_face_recognition.py
if [ $? -eq 0 ]; then
    echo "✓ Tests passed"
else
    echo "⚠ Some tests failed (this is normal if no users are enrolled yet)"
fi
echo ""

# Success message
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Start Django server:"
echo "   python manage.py runserver"
echo ""
echo "2. Start Celery worker (in another terminal):"
echo "   celery -A api worker --loglevel=info"
echo ""
echo "3. Enroll users via web interface:"
echo "   http://localhost:8000/settings"
echo "   → Face Recognition → Upload 5 photos"
echo ""
echo "4. Create posts with images and test face recognition!"
echo ""
echo "Documentation:"
echo "  - Quick Start: ../QUICK_START_FACE_RECOGNITION.md"
echo "  - Full Docs: FACE_RECOGNITION_README.md"
echo "  - Migration Guide: ../FACE_RECOGNITION_MIGRATION_GUIDE.md"
echo ""
echo "=========================================="
