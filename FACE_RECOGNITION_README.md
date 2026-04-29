# Custom Face Recognition System

This document describes the custom face recognition system that replaces AWS Rekognition with open-source facial embeddings.

---

## Architecture Overview

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    User Uploads 5 Photos                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              FaceRecognitionService                          │
│  - Extracts face embeddings using DeepFace                   │
│  - Stores embeddings in database (base64-encoded)            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  FaceEnrollment Model                        │
│  - user: ForeignKey to User                                  │
│  - embeddings: JSONField (list of base64 strings)            │
│  - embedding_model: CharField (e.g., "Facenet512")           │
│  - is_enrolled: Boolean                                      │
└─────────────────────────────────────────────────────────────┘

                    When Friend Posts Photo
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Celery Task Triggered                     │
│  (replaces AWS Lambda)                                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│         process_post_for_face_recognition()                  │
│  1. Extract faces from photo                                 │
│  2. Generate embeddings for each face                        │
│  3. Compare with all enrolled user embeddings                │
│  4. Find matches above threshold (cosine similarity)         │
│  5. Apply privacy filters (friends only, tagging enabled)    │
│  6. Create TagSuggestion records                             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   TagSuggestion Model                        │
│  - post: ForeignKey to Post                                  │
│  - suggested_user: ForeignKey to User                        │
│  - confidence: Float (similarity score 0-100)                │
│  - bounding_box: JSONField (face location)                   │
│  - status: pending/accepted/rejected                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Files

### Services

1. **`recognition/services/face_embedding.py`**
   - Low-level face embedding operations
   - Uses DeepFace library
   - Handles face detection, embedding extraction, and comparison
   - Model-agnostic (supports multiple models)

2. **`recognition/services/face_recognition_service.py`**
   - High-level face recognition API
   - Manages database operations
   - Enrollment, deletion, status checking
   - Face search across all enrolled users

3. **`recognition/services/async_face_recognition.py`**
   - Asynchronous processing logic
   - Replaces AWS Lambda functionality
   - Called by Celery tasks

### Views

**`recognition/views.py`** - Updated to use custom service:
- `enroll_face_view()` - Upload and process enrollment photos
- `enrollment_status_view()` - Check enrollment status
- `delete_face_data_view()` - Delete user's face data
- `pending_tags_view()` - Get pending tag suggestions
- `review_tag_view()` - Accept/reject tag suggestions

### Tasks

**`recognition/tasks.py`** - Celery background tasks:
- `process_photo_for_tags()` - Process new posts for face recognition

### Models

**`recognition/models.py`**:
- `FaceEnrollment` - Stores user face embeddings
- `TagSuggestion` - Pending/accepted/rejected tags
- `PrivacySettings` - User privacy preferences

---

## Workflow Details

### 1. User Enrollment

```python
# User uploads 5 photos via frontend
POST /api/recognition/faces/enroll/
Content-Type: multipart/form-data
images: [file1, file2, file3, file4, file5]

# Backend processing:
1. FaceRecognitionService.enroll_user_faces()
2. For each image:
   - FaceEmbeddingService.extract_embeddings()
   - Detect face using RetinaFace
   - Generate 512-dim embedding using Facenet512
   - Convert to base64 string
3. Store all embeddings in FaceEnrollment.embeddings
4. Set is_enrolled = True
```

### 2. Face Recognition on New Post

```python
# User creates post with image
POST /api/community/posts/
Content-Type: multipart/form-data
content: "Check out this photo!"
image: photo.jpg

# Backend processing:
1. Save post to database
2. Trigger Celery task: process_photo_for_tags.delay(post.id)
3. Task execution:
   - Load image bytes
   - Extract all faces from image
   - For each face:
     * Generate embedding
     * Compare with all enrolled users
     * Calculate cosine similarity
     * Keep matches above threshold (default 70%)
   - Apply privacy filters:
     * User has face_tagging_enabled = True
     * User is friends with post author
   - Create TagSuggestion for each match
```

### 3. User Reviews Tags

```python
# User sees pending tags in settings
GET /api/recognition/tags/pending/

# User accepts or rejects
POST /api/recognition/tags/{tag_id}/review/
{"action": "accept"}  # or "reject"

# If accepted:
- TagSuggestion.status = 'accepted'
- Post.tagged_users.add(user)
```

---

## Face Embedding Details

### Embedding Generation

```python
# Input: Image bytes
# Output: 512-dimensional vector (for Facenet512)

Example embedding (truncated):
[0.123, -0.456, 0.789, ..., 0.234]  # 512 numbers

# Stored as base64 in database:
"AAAAAAAA8D8AAAAAAADwPwAAAAAAAPA/..."
```

### Similarity Calculation

```python
def compare_embeddings(emb1, emb2):
    # Normalize vectors
    emb1 = emb1 / ||emb1||
    emb2 = emb2 / ||emb2||
    
    # Cosine similarity
    similarity = emb1 · emb2  # Dot product
    
    # Convert to percentage (0-100)
    score = (similarity + 1) * 50
    
    return score

# Example:
# similarity = 0.9 → score = 95% (very similar)
# similarity = 0.4 → score = 70% (threshold)
# similarity = 0.0 → score = 50% (neutral)
# similarity = -1.0 → score = 0% (opposite)
```

---

## Configuration

### Model Selection

**Available Models:**

| Model | Embedding Size | Speed | Accuracy | Memory |
|-------|---------------|-------|----------|--------|
| Facenet512 | 512 | ⚡⚡ | ⭐⭐⭐⭐ | 90 MB |
| ArcFace | 512 | ⚡⚡ | ⭐⭐⭐⭐⭐ | 130 MB |
| Facenet | 128 | ⚡⚡⚡ | ⭐⭐⭐ | 90 MB |
| VGG-Face | 2622 | ⚡ | ⭐⭐⭐⭐ | 500 MB |
| OpenFace | 128 | ⚡⚡⚡ | ⭐⭐ | 30 MB |
| Dlib | 128 | ⚡⚡ | ⭐⭐⭐ | 100 MB |

**Recommendation:** Use `Facenet512` for best balance of speed and accuracy.

### Detector Selection

**Available Detectors:**

| Detector | Speed | Accuracy | Notes |
|----------|-------|----------|-------|
| retinaface | ⚡⚡ | ⭐⭐⭐⭐⭐ | Best accuracy, recommended |
| mtcnn | ⚡⚡ | ⭐⭐⭐⭐ | Good alternative |
| opencv | ⚡⚡⚡⚡ | ⭐⭐ | Fast but less accurate |
| ssd | ⚡⚡⚡ | ⭐⭐⭐ | Balanced |

**Recommendation:** Use `retinaface` for best face detection.

### Threshold Tuning

```python
# In api/settings.py
FACE_RECOGNITION_THRESHOLD = 70.0

# Guidelines:
# 60-65: Very lenient (more false positives)
# 65-70: Lenient (good for varied conditions)
# 70-75: Balanced (recommended)
# 75-80: Strict (fewer false positives)
# 80-90: Very strict (high confidence only)
```

---

## Performance Optimization

### CPU Optimization

```python
# Reduce TensorFlow logging
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

# Use faster model
FACE_RECOGNITION_MODEL = 'Facenet'  # 128-dim instead of 512

# Use faster detector
FACE_DETECTOR_BACKEND = 'opencv'
```

### GPU Acceleration

```bash
# Install GPU version
pip uninstall tensorflow
pip install tensorflow-gpu

# Verify GPU is detected
python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

### Caching (Future Enhancement)

```python
# Cache model loading (models are loaded once per worker)
# DeepFace automatically caches models in ~/.deepface/weights/

# For faster repeated processing, consider:
# - Redis cache for embeddings
# - Preload models on worker startup
```

---

## Privacy & Security

### Data Storage

- **Embeddings**: Stored as base64-encoded strings in database
- **Original Photos**: Not stored (only embeddings)
- **Reversibility**: Embeddings cannot be reversed to original photos

### Privacy Controls

1. **Opt-in**: Users must explicitly enable face tagging
2. **Friends Only**: Only friends can tag each other
3. **Manual Approval**: Tags are pending until user accepts
4. **Deletion**: Users can delete all face data anytime

### GDPR Compliance

- ✅ Right to access: Users can view their enrollment status
- ✅ Right to deletion: Users can delete face data
- ✅ Consent: Explicit opt-in required
- ✅ Data minimization: Only embeddings stored, not photos

---

## Troubleshooting

### Common Issues

**1. "No face detected in image"**
```python
# Solutions:
- Ensure face is clearly visible and well-lit
- Try different detector: FACE_DETECTOR_BACKEND = 'mtcnn'
- Check image quality (not too small, not blurry)
```

**2. "Too many false positives"**
```python
# Solutions:
- Increase threshold: FACE_RECOGNITION_THRESHOLD = 80.0
- Use more accurate model: FACE_RECOGNITION_MODEL = 'ArcFace'
- Ensure enrollment photos are high quality
```

**3. "Missing matches"**
```python
# Solutions:
- Lower threshold: FACE_RECOGNITION_THRESHOLD = 65.0
- Ensure user enrolled with varied angles/lighting
- Check privacy settings (face_tagging_enabled)
```

**4. "Slow processing"**
```python
# Solutions:
- Use GPU: pip install tensorflow-gpu
- Use faster model: FACE_RECOGNITION_MODEL = 'Facenet'
- Use faster detector: FACE_DETECTOR_BACKEND = 'opencv'
- Ensure Celery is running (async processing)
```

---

## Testing

### Run Test Suite

```bash
cd django-viking-roots
python test_face_recognition.py
```

### Manual Testing

```bash
# 1. Start Django
python manage.py runserver

# 2. Start Celery (in another terminal)
celery -A api worker --loglevel=info

# 3. Test enrollment
curl -X POST http://localhost:8000/api/recognition/faces/enroll/ \
  -F "images=@photo1.jpg" \
  -F "images=@photo2.jpg" \
  -F "images=@photo3.jpg" \
  -F "images=@photo4.jpg" \
  -F "images=@photo5.jpg"

# 4. Create post with image
curl -X POST http://localhost:8000/api/community/posts/ \
  -F "content=Test" \
  -F "image=@test.jpg"

# 5. Check pending tags
curl http://localhost:8000/api/recognition/tags/pending/
```

---

## Migration from AWS Rekognition

See [FACE_RECOGNITION_MIGRATION_GUIDE.md](../FACE_RECOGNITION_MIGRATION_GUIDE.md) for detailed migration instructions.

**Quick Summary:**
1. Install dependencies: `pip install -r requirements-face-recognition.txt`
2. Run migrations: `python manage.py migrate recognition`
3. Update settings with model configuration
4. Users re-enroll through web interface
5. System automatically uses new service

---

## Future Enhancements

### Potential Improvements

1. **Face Clustering**: Group similar faces for better organization
2. **Age/Gender Detection**: Additional metadata for faces
3. **Emotion Recognition**: Detect facial expressions
4. **Multi-face Tracking**: Track same person across multiple photos
5. **Quality Scoring**: Reject low-quality enrollment photos
6. **Incremental Learning**: Improve embeddings over time
7. **Face Verification**: Two-factor authentication using face

### Performance Enhancements

1. **Batch Processing**: Process multiple images in parallel
2. **Embedding Cache**: Cache frequently accessed embeddings
3. **Model Quantization**: Reduce model size for faster inference
4. **Distributed Processing**: Use multiple workers for scaling

---

## API Reference

### Enrollment

```python
POST /api/recognition/faces/enroll/
Content-Type: multipart/form-data

Request:
  images: List[File]  # 1-10 images

Response:
  {
    "message": "Successfully enrolled 5 face(s)",
    "face_count": 5
  }
```

### Status

```python
GET /api/recognition/faces/status/

Response:
  {
    "is_enrolled": true,
    "face_count": 5,
    "model": "Facenet512",
    "last_updated": "2024-01-15T10:30:00Z"
  }
```

### Delete

```python
DELETE /api/recognition/faces/delete/

Response:
  {
    "message": "Biometric face data deleted successfully"
  }
```

### Pending Tags

```python
GET /api/recognition/tags/pending/

Response:
  {
    "pending_tags": [
      {
        "id": 1,
        "post_id": 42,
        "post_image": "https://...",
        "uploaded_by": "john_doe",
        "confidence": 85.5,
        "created_at": "2024-01-15T10:30:00Z"
      }
    ]
  }
```

### Review Tag

```python
POST /api/recognition/tags/{tag_id}/review/
Content-Type: application/json

Request:
  {
    "action": "accept"  # or "reject"
  }

Response:
  {
    "message": "Tag accepted successfully"
  }
```

---

## Support

For issues or questions:
- Check logs: `python manage.py runserver` and `celery -A api worker --loglevel=debug`
- Run test suite: `python test_face_recognition.py`
- Review DeepFace docs: https://github.com/serengil/deepface
- Check TensorFlow docs: https://www.tensorflow.org/

---

## License

This custom face recognition system uses:
- DeepFace (MIT License)
- TensorFlow (Apache 2.0)
- Pre-trained models (various licenses - check model documentation)

Ensure compliance with model licenses for commercial use.
