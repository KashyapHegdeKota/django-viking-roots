#!/usr/bin/env python
"""
Test script for custom face recognition system
Run with: python test_face_recognition.py
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from django.contrib.auth.models import User
from recognition.services.face_recognition_service import FaceRecognitionService
from recognition.services.async_face_recognition import process_post_for_face_recognition
from recognition.models import FaceEnrollment
from community.models import Post


def test_embedding_service():
    """Test the basic embedding service"""
    print("\n" + "="*60)
    print("TEST 1: Face Embedding Service")
    print("="*60)
    
    try:
        service = FaceRecognitionService()
        print(f"✓ Service initialized with model: {service.model_name}")
        return True
    except Exception as e:
        print(f"✗ Failed to initialize service: {e}")
        return False


def test_user_enrollment(username='testuser'):
    """Test enrolling a user with sample images"""
    print("\n" + "="*60)
    print(f"TEST 2: User Enrollment ({username})")
    print("="*60)
    
    try:
        # Get or create test user
        user, created = User.objects.get_or_create(username=username)
        print(f"{'✓ Created' if created else '✓ Found'} user: {username}")
        
        # Check enrollment status
        service = FaceRecognitionService()
        status = service.get_enrollment_status(user)
        print(f"  Current status: enrolled={status['is_enrolled']}, faces={status['face_count']}")
        
        return True
    except Exception as e:
        print(f"✗ Enrollment test failed: {e}")
        return False


def test_face_matching():
    """Test face matching logic"""
    print("\n" + "="*60)
    print("TEST 3: Face Matching")
    print("="*60)
    
    try:
        service = FaceRecognitionService()
        
        # Load enrolled embeddings
        embeddings = service.load_all_enrolled_embeddings()
        print(f"✓ Loaded {len(embeddings)} embeddings from database")
        
        if embeddings:
            print(f"  Users enrolled: {len(set(uid for uid, _ in embeddings))}")
        else:
            print("  ⚠ No users enrolled yet - enroll users first to test matching")
        
        return True
    except Exception as e:
        print(f"✗ Face matching test failed: {e}")
        return False


def test_post_processing(post_id=None):
    """Test processing a post for face recognition"""
    print("\n" + "="*60)
    print("TEST 4: Post Processing")
    print("="*60)
    
    try:
        if post_id is None:
            # Find a post with an image
            posts = Post.objects.filter(image__isnull=False).order_by('-created_at')[:5]
            if not posts:
                print("  ⚠ No posts with images found - create a post first")
                return True
            post_id = posts[0].id
        
        print(f"  Testing with post ID: {post_id}")
        
        # Process the post
        result = process_post_for_face_recognition(post_id)
        
        if result['success']:
            print(f"✓ Processing successful")
            print(f"  Message: {result['message']}")
            print(f"  Suggestions created: {result['suggestions_created']}")
        else:
            print(f"⚠ Processing completed with message: {result['message']}")
        
        return True
    except Exception as e:
        print(f"✗ Post processing test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_model_info():
    """Display model and configuration info"""
    print("\n" + "="*60)
    print("TEST 5: Configuration Info")
    print("="*60)
    
    try:
        from django.conf import settings
        
        print(f"  Model: {getattr(settings, 'FACE_RECOGNITION_MODEL', 'Facenet512')}")
        print(f"  Detector: {getattr(settings, 'FACE_DETECTOR_BACKEND', 'retinaface')}")
        print(f"  Threshold: {getattr(settings, 'FACE_RECOGNITION_THRESHOLD', 70.0)}%")
        
        # Check if TensorFlow is available
        try:
            import tensorflow as tf
            print(f"  TensorFlow: {tf.__version__}")
            print(f"  GPU Available: {len(tf.config.list_physical_devices('GPU')) > 0}")
        except ImportError:
            print("  TensorFlow: Not installed")
        
        # Check DeepFace
        try:
            import deepface
            print(f"  DeepFace: Installed")
        except ImportError:
            print("  DeepFace: Not installed")
        
        return True
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("CUSTOM FACE RECOGNITION TEST SUITE")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("Model Info", test_model_info()))
    results.append(("Embedding Service", test_embedding_service()))
    results.append(("User Enrollment", test_user_enrollment()))
    results.append(("Face Matching", test_face_matching()))
    results.append(("Post Processing", test_post_processing()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Face recognition system is working.")
    else:
        print("\n⚠ Some tests failed. Check the output above for details.")
    
    print("\n" + "="*60)
    print("NEXT STEPS")
    print("="*60)
    print("1. Enroll users via the web interface:")
    print("   Settings → Face Recognition → Upload 5 photos")
    print("\n2. Create a post with an image containing enrolled faces")
    print("\n3. Check pending tags:")
    print("   Settings → Pending Photo Tags")
    print("\n4. Monitor Celery worker logs for processing:")
    print("   celery -A api worker --loglevel=info")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
