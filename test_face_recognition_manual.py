#!/usr/bin/env python
"""
Manual test script for face recognition (no Celery/Redis needed)
Run with: python test_face_recognition_manual.py
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


def test_enrollment_status():
    """Check if users are enrolled"""
    print("\n" + "="*60)
    print("ENROLLMENT STATUS")
    print("="*60)
    
    enrollments = FaceEnrollment.objects.filter(is_enrolled=True)
    
    if not enrollments:
        print("❌ No users enrolled yet")
        print("\nTo enroll:")
        print("1. Go to http://localhost:8000/settings")
        print("2. Upload 5 photos in Face Recognition section")
        return False
    
    for enrollment in enrollments:
        print(f"\n✓ User: {enrollment.user.username}")
        print(f"  Faces: {len(enrollment.embeddings)}")
        print(f"  Model: {enrollment.embedding_model}")
        print(f"  Updated: {enrollment.last_updated}")
    
    return True


def test_face_recognition_on_post(post_id=None):
    """Test face recognition on a specific post"""
    print("\n" + "="*60)
    print("FACE RECOGNITION TEST")
    print("="*60)
    
    # Find a post with an image
    if post_id:
        posts = Post.objects.filter(id=post_id, image__isnull=False)
    else:
        posts = Post.objects.filter(image__isnull=False).order_by('-created_at')[:5]
    
    if not posts:
        print("❌ No posts with images found")
        print("\nTo test:")
        print("1. Create a post with an image")
        print("2. Run this script again")
        return
    
    post = posts[0]
    print(f"\n📸 Testing with Post ID: {post.id}")
    print(f"   Author: {post.author.username}")
    print(f"   Image: {post.image.name if post.image else 'None'}")
    
    print("\n⏳ Processing face recognition...")
    result = process_post_for_face_recognition(post.id)
    
    print(f"\n{'✓' if result['success'] else '✗'} Result: {result['message']}")
    print(f"   Suggestions created: {result['suggestions_created']}")
    
    if result['suggestions_created'] > 0:
        print("\n🎉 Success! Face recognition is working!")
        print("\nTo see tags:")
        print("1. Go to http://localhost:8000/settings")
        print("2. Check 'Pending Photo Tags' section")
    elif result['success']:
        print("\n⚠ No matches found. This could mean:")
        print("  - No enrolled faces in the photo")
        print("  - Faces don't match enrolled users")
        print("  - Photo quality is too low")
    
    return result


def main():
    """Run all manual tests"""
    print("\n" + "="*60)
    print("MANUAL FACE RECOGNITION TEST")
    print("(No Celery/Redis needed)")
    print("="*60)
    
    # Test 1: Check enrollments
    has_enrollments = test_enrollment_status()
    
    if not has_enrollments:
        print("\n" + "="*60)
        print("⚠ Please enroll at least one user first")
        print("="*60)
        return
    
    # Test 2: Test face recognition
    test_face_recognition_on_post()
    
    print("\n" + "="*60)
    print("MANUAL TEST COMPLETE")
    print("="*60)
    print("\nNext steps:")
    print("1. Check http://localhost:8000/settings for pending tags")
    print("2. Accept or reject the tag suggestions")
    print("3. Install Redis for automatic processing")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
