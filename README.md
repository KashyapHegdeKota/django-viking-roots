# Gimli Saga (Capstone-VikingRoots)

**GitHub Repository:** https://github.com/KashyapHegdeKota/django-viking-roots 

## Project Summary
**Gimli Saga** is a comprehensive heritage and genealogy platform designed to help users document, explore, and preserve their family history. The standout feature is a custom, privacy-focused, CPU-optimized Face Recognition System that automatically identifies individuals in historical and contemporary photos without relying on expensive third-party APIs.

## Project Checklist

- [x] A brief summary of the project and its intended use.
- [x] Installation instructions and technical documentation on how to run any code, and/or versioning of any libraries used to replicate your setup.
- [x] User guide explaining intended usage.
- [ ] GitHub repository link provided above.

## Installation & Technical Documentation

This project is a monorepo consisting of a Django REST API backend and a React (Vite/TypeScript) Single Page Application frontend.

### Prerequisites
- **Node.js**: v18+ (for frontend)
- **Python**: v3.8+ (for backend)
- **Redis**: Required for background task processing (Celery face recognition tasks)
- **Database**: SQLite (default for local development) or PostgreSQL

### Backend Setup (Django)

1. **Navigate to the backend directory:**
   ```bash
   cd django-viking-roots
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On Mac/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   # Core dependencies
   pip install -r requirements.txt
   
   # Face recognition specific dependencies
   pip install -r requirements-face-recognition.txt
   ```
   *Key libraries: Django (4.2.15), djangorestframework (3.16.1), Celery (5.4.0), Redis (5.0.8), DeepFace, TensorFlow.*

4. **Run database migrations:**
   ```bash
   python manage.py migrate
   ```

5. **Start the development server:**
   ```bash
   python manage.py runserver
   ```
   The API backend will be available at `http://localhost:8000`.

6. **Start background workers (in a separate terminal):**
   This is required for the face recognition and image processing to work.
   ```bash
   cd django-viking-roots
   # Ensure your virtual environment is activated
   celery -A api worker --loglevel=info
   ```
   *(Note: On Windows, you may need to append `--pool=solo` to the command).*

### Frontend Setup (React)

1. **Navigate to the frontend directory:**
   ```bash
   cd frontend-viking-roots
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```
   *Key libraries: React (19.1.1), Vite (7.1.7), TailwindCSS (4.2.0), Radix UI primitives, React Router DOM (7.9.3).*

3. **Start the development server:**
   ```bash
   npm run dev
   ```
   The frontend will be available at the local URL provided by Vite (usually `http://localhost:5173`).

## User Guide

1. **Creating an Account & Profile:**
   - Navigate to the local frontend URL.
   - Register for a new account and fill out your heritage profile.
   
2. **Family Connections:**
   - Add family members and build your family tree using the interactive UI.
   - Send and accept connection requests to establish a network of relatives.

3. **Face Recognition & Tagging:**
   - **Enrollment:** Go to **Settings → Face Recognition** and upload 5 clear photos of your face. The system will extract your facial embeddings.
   - **Privacy:** Enable "Face Tagging" in your privacy settings and set your preferred scope (e.g., manual approval, friends only).
   - **Usage:** When you or a connected user uploads a photo to the community feed, the Celery background worker automatically detects faces and compares them to enrolled users.
   - **Review:** Go to **Settings → Pending Photo Tags** to review, accept, or reject automatically suggested tags on photos.

4. **Community Feed:**
   - Share historical photos, stories, and updates with your family network.
   - View tagged individuals in photos seamlessly.
