# Render Deployment Checklist

## ✅ Pre-Deployment Checklist

### Files Updated:
- ✅ `requirements.txt` - Fixed dependencies (gunicorn, python-dotenv, google-generativeai)
- ✅ `api/settings.py` - Added Render support and GEMINI_API_KEY
- ✅ `api/wsgi.py` - Already configured with 'application'
- ✅ `render.yaml` - Build and start commands configured
- ✅ `questionaire/views.py` - Using JsonResponse (no REST framework needed)

### Environment Variables to Set on Render:

**Required:**
1. `DATABASE_URL` - Auto-populated by Render PostgreSQL
2. `SECRET_KEY` - Generate a secure Django secret key
3. `GEMINI_API_KEY` - Your Google Gemini API key for the questionnaire feature
4. `DEBUG` - Set to `False`
5. `PYTHON_VERSION` - `3.11.0`

**Optional:**
6. `RENDER_EXTERNAL_HOSTNAME` - If using custom domain

---

## 🚀 Deployment Steps

### 1. Commit and Push Changes
```bash
git add .
git commit -m "Prepare for Render deployment with questionnaire feature"
git push origin main
```

### 2. Create PostgreSQL Database on Render
1. Go to https://render.com/dashboard
2. Click "New +" → "PostgreSQL"
3. Name: `django-viking-roots-db`
4. Choose plan (Free or Starter)
5. Click "Create Database"
6. **Copy the Internal Database URL** (you'll need this)

### 3. Create Web Service on Render
1. Click "New +" → "Web Service"
2. Connect your GitHub repo: `KashyapHegdeKota/django-viking-roots`
3. Configure:
   - **Name**: `django-viking-roots`
   - **Runtime**: `Python 3`
   - **Branch**: `main` (or your current branch)
   - **Build Command**: `pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate`
   - **Start Command**: `gunicorn api.wsgi:application`
   - **Plan**: Free or Starter

### 4. Set Environment Variables
In the Render web service dashboard, go to "Environment" tab and add:

```
DATABASE_URL = <paste your PostgreSQL Internal Database URL>
SECRET_KEY = <generate using: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
GEMINI_API_KEY = <your Google Gemini API key>
DEBUG = False
PYTHON_VERSION = 3.11.0
```

### 5. Get Your Gemini API Key
If you don't have one:
1. Go to https://aistudio.google.com/app/apikey
2. Sign in with Google
3. Create a new API key
4. Copy and paste it into Render's `GEMINI_API_KEY` environment variable

### 6. Deploy
Click "Create Web Service" - Render will automatically deploy!

---

## 🧪 Testing Your Deployment

Once deployed, your Render URL will be: `https://django-viking-roots.onrender.com`

### Test Endpoints:

1. **Health Check** (if you have one):
   ```
   GET https://django-viking-roots.onrender.com/
   ```

2. **Start Interview**:
   ```bash
   curl -X POST https://django-viking-roots.onrender.com/api/questionaire/start/
   ```

3. **Send Message**:
   ```bash
   curl -X POST https://django-viking-roots.onrender.com/api/questionaire/message/ \
     -H "Content-Type: application/json" \
     -d '{"message": "My name is John", "chat_history": []}'
   ```

4. **Authentication Endpoints**:
   ```
   POST /api/register/
   POST /api/login/
   POST /api/logout/
   ```

---

## ⚠️ Important Notes

### Free Tier Limitations:
- Web services spin down after 15 minutes of inactivity
- First request may take 30-50 seconds (cold start)
- PostgreSQL free tier has 90-day expiration

### After First Deployment:
1. Note your Render URL
2. Update CORS settings if needed for your frontend
3. Update CSRF_TRUSTED_ORIGINS if needed

### If You Encounter Errors:
1. Check Render logs in the dashboard
2. Verify all environment variables are set
3. Make sure GEMINI_API_KEY is valid
4. Check that DATABASE_URL is connected

---

## 🔄 Future Deployments

After the initial setup, future deployments are automatic:
1. Push code to GitHub
2. Render automatically rebuilds and redeploys
3. No manual intervention needed!

---

## 📝 Generate Secret Key

Run this locally to generate a new SECRET_KEY:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copy the output and use it as your SECRET_KEY in Render.
