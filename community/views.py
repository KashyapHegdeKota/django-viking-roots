import json
import traceback
import boto3
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import Q
from django.conf import settings

# Import from THIS app
from .models import (
    AncestorMatch, Post, PostLike, Comment,
    Group, GroupMembership, GroupPost, FamilyConnection,
)
from .services.matching_service import FamilyMatchingService
from .services.tree_merge_service import FamilyTreeMergeService

# Recognition task
try:
    from recognition.tasks import process_photo_for_tags
except ImportError:
    process_photo_for_tags = None

def get_user_for_request(request):
    """Get authenticated user or create test user"""
    if request.user.is_authenticated:
        return request.user
    else:
        user, _ = User.objects.get_or_create(username='testuser')
        return user

@csrf_exempt
def find_potential_matches(request):
    """Find potential family connections for current user"""
    if request.method == 'GET':
        try:
            user = get_user_for_request(request)
            matching_service = FamilyMatchingService()
            
            matches = matching_service.suggest_ancestor_matches_for_user(user)
            connections = matching_service.find_family_connections(user)
            
            return JsonResponse({
                'potential_matches': [
                    {
                        'id': m.id,
                        'your_ancestor': m.ancestor1.name if m.ancestor1.user == user else m.ancestor2.name,
                        'their_ancestor': m.ancestor2.name if m.ancestor1.user == user else m.ancestor1.name,
                        'other_user': m.ancestor2.user.username if m.ancestor1.user == user else m.ancestor1.user.username,
                        'confidence': m.confidence_score,
                        'matching_attributes': m.matching_attributes
                    }
                    for m in matches
                ],
                'family_connections': [
                    {
                        'user': conn['user'].username,
                        'shared_ancestors': conn['shared_ancestors'],
                        'likely_relationship': conn['relationship_hints'][0] if conn['relationship_hints'] else 'related'
                    }
                    for conn in connections
                ]
            }, status=200)
            
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)

@csrf_exempt
def confirm_ancestor_match(request, match_id):
    """Confirm that two ancestors are the same person"""
    if request.method == 'POST':
        try:
            user = get_user_for_request(request)
            match = get_object_or_404(AncestorMatch, id=match_id)
            
            if match.ancestor1.user != user and match.ancestor2.user != user:
                return JsonResponse({'error': 'Permission denied'}, status=403)
                
            match.status = 'confirmed'
            match.reviewed_by = user
            match.reviewed_at = timezone.now()
            match.save()
            
            matching_service = FamilyMatchingService()
            connection = matching_service.create_family_connection(
                match.ancestor1.user,
                match.ancestor2.user,
                matching_service.infer_user_relationship(
                    match.ancestor1.relation,
                    match.ancestor2.relation
                ),
                match.ancestor1.name,
                match.confidence_score
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Match confirmed and family connection created'
            }, status=200)
            
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)

@csrf_exempt
def get_merged_family_tree(request):
    """Get merged family tree for user and their connections"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user = get_user_for_request(request)
            
            user_ids = data.get('user_ids', [user.id])
            users = User.objects.filter(id__in=user_ids)
            
            merge_service = FamilyTreeMergeService(users)
            merged_tree = merge_service.build_merged_tree()
            
            return JsonResponse(merged_tree, status=200)
            
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


# =============================================================================
# Direct Family Connections (Friendships)
# =============================================================================

@csrf_exempt
def list_connections(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    user = request.user
    from form.models import UserProfile

    def _get_user_info(u):
        try:
            profile = UserProfile.objects.get(user=u)
            pic = profile.profile_picture.url if profile.profile_picture else None
        except UserProfile.DoesNotExist:
            pic = None
        return {'id': u.id, 'username': u.username, 'profile_picture_url': pic}

    try:
        # Accepted connections
        accepted = FamilyConnection.objects.filter(
            Q(user1=user) | Q(user2=user), status='accepted'
        )
        friends = []
        for c in accepted:
            friend = c.user2 if c.user1 == user else c.user1
            friends.append(_get_user_info(friend))

        # Pending requests received
        pending = FamilyConnection.objects.filter(user2=user, status='pending')
        requests_received = []
        for c in pending:
            req_info = _get_user_info(c.user1)
            req_info['connection_id'] = c.id
            requests_received.append(req_info)

        return JsonResponse({
            'friends': friends,
            'requests_received': requests_received
        })
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def send_connection_request(request, user_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    if request.user.id == user_id:
        return JsonResponse({'error': 'Cannot connect with yourself'}, status=400)

    try:
        target_user = User.objects.get(id=user_id)
        
        # Check if connection already exists
        existing = FamilyConnection.objects.filter(
            Q(user1=request.user, user2=target_user) | Q(user1=target_user, user2=request.user)
        ).first()

        if existing:
            return JsonResponse({'error': f'Connection already exists with status: {existing.status}'}, status=400)

        # Create pending connection
        FamilyConnection.objects.create(
            user1=request.user,
            user2=target_user,
            connection_type='Friend',
            confidence_score=1.0,
            status='pending'
        )
        return JsonResponse({'message': 'Connection request sent successfully'}, status=201)

    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def accept_connection_request(request, connection_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        connection = get_object_or_404(FamilyConnection, id=connection_id, user2=request.user, status='pending')
        connection.status = 'accepted'
        connection.save()
        return JsonResponse({'message': 'Connection request accepted'}, status=200)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

# =============================================================================
# Social Media Views - Posts, Tagging, Likes, Comments
# =============================================================================

def _serialize_post(post, current_user=None):
    """Serialize a post for JSON response."""
    from form.models import UserProfile
    try:
        author_profile = UserProfile.objects.get(user=post.author)
        profile_picture_url = author_profile.profile_picture.url if author_profile.profile_picture else None
    except UserProfile.DoesNotExist:
        profile_picture_url = None

    tagged = [
        {'id': u.id, 'username': u.username}
        for u in post.tagged_users.all()
    ]
    like_count = post.likes.count()
    comment_count = post.comments.count()
    liked_by_me = False
    if current_user and current_user.is_authenticated:
        liked_by_me = post.likes.filter(user=current_user).exists()

    # Check if this post belongs to a group
    group_info = None
    try:
        gp = post.group_context
        group_info = {'id': gp.group.id, 'name': gp.group.name}
    except GroupPost.DoesNotExist:
        pass

    return {
        'id': post.id,
        'author': {
            'id': post.author.id,
            'username': post.author.username,
            'profile_picture_url': profile_picture_url,
        },
        'content': post.content,
        'image_url': post.image.url if post.image else None,
        'tagged_users': tagged,
        'like_count': like_count,
        'comment_count': comment_count,
        'liked_by_me': liked_by_me,
        'group': group_info,
        'created_at': post.created_at.isoformat(),
        'updated_at': post.updated_at.isoformat(),
    }


def _serialize_comment(comment):
    """Serialize a comment for JSON response."""
    from form.models import UserProfile
    try:
        author_profile = UserProfile.objects.get(user=comment.author)
        profile_picture_url = author_profile.profile_picture.url if author_profile.profile_picture else None
    except UserProfile.DoesNotExist:
        profile_picture_url = None

    return {
        'id': comment.id,
        'author': {
            'id': comment.author.id,
            'username': comment.author.username,
            'profile_picture_url': profile_picture_url,
        },
        'content': comment.content,
        'created_at': comment.created_at.isoformat(),
    }


@csrf_exempt
def search_users(request):
    """Search users by username for tagging."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    query = request.GET.get('q', '').strip()
    if len(query) < 1:
        return JsonResponse({'users': []})

    users = User.objects.filter(
        Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query)
    ).exclude(id=request.user.id if request.user.is_authenticated else -1)[:10]

    from form.models import UserProfile
    results = []
    for u in users:
        try:
            profile = UserProfile.objects.get(user=u)
            pic_url = profile.profile_picture.url if profile.profile_picture else None
        except UserProfile.DoesNotExist:
            pic_url = None
        results.append({
            'id': u.id,
            'username': u.username,
            'full_name': u.get_full_name() or u.username,
            'profile_picture_url': pic_url,
        })

    return JsonResponse({'users': results})


@csrf_exempt
def create_post(request):
    """Create a new post with optional image and tagged users."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        content = request.POST.get('content', '').strip()
        if not content and not request.FILES.get('image'):
            return JsonResponse({'error': 'Post must have content or an image'}, status=400)

        post = Post.objects.create(
            author=request.user,
            content=content,
        )

        # Handle image upload
        image_file = request.FILES.get('image')
        if image_file:
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
            if image_file.content_type not in allowed_types:
                post.delete()
                return JsonResponse({'error': 'Invalid image type'}, status=400)
            if image_file.size > 10 * 1024 * 1024:
                post.delete()
                return JsonResponse({'error': 'Image too large (max 10MB)'}, status=400)
            post.image = image_file
            post.save()
            
            # Trigger AWS Lambda for face recognition
            try:
                lambda_client = boto3.client(
                    'lambda',
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_S3_REGION_NAME
                )
                
                payload = {
                    'post_id': post.id,
                    'image_url': post.image.url,
                    'webhook_url': request.build_absolute_uri('/api/recognition/webhook/lambda-recognition/'),
                    'webhook_key': settings.LAMBDA_WEBHOOK_KEY,
                    'collection_id': settings.AWS_REKOGNITION_COLLECTION_ID
                }
                
                lambda_client.invoke(
                    FunctionName=settings.AWS_LAMBDA_FUNCTION_NAME,
                    InvocationType='Event', # Asynchronous
                    Payload=json.dumps(payload)
                )
            except Exception as e:
                print(f"Error invoking Lambda: {e}")

        # Handle tagged users
        tagged_ids = request.POST.get('tagged_user_ids', '')
        if tagged_ids:
            try:
                ids = json.loads(tagged_ids)
                if isinstance(ids, list):
                    users_to_tag = User.objects.filter(id__in=ids)
                    post.tagged_users.set(users_to_tag)
            except (json.JSONDecodeError, TypeError):
                pass

        # Handle group context
        group_id = request.POST.get('group_id')
        if group_id:
            try:
                group = Group.objects.get(id=group_id)
                # Verify user is a member
                if GroupMembership.objects.filter(user=request.user, group=group, status='active').exists():
                    GroupPost.objects.create(group=group, post=post)
            except Group.DoesNotExist:
                pass

        return JsonResponse({
            'message': 'Post created successfully',
            'post': _serialize_post(post, request.user),
        }, status=201)

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': f'Failed to create post: {str(e)}'}, status=500)


@csrf_exempt
def list_posts(request):
    """Get the social feed - all posts or filtered."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        offset = (page - 1) * per_page

        # Filter options
        user_id = request.GET.get('user_id')
        group_id = request.GET.get('group_id')

        posts = Post.objects.select_related('author').prefetch_related('tagged_users', 'likes', 'comments')

        if user_id:
            posts = posts.filter(author_id=user_id)
        elif group_id:
            posts = posts.filter(group_context__group_id=group_id)

        total = posts.count()
        posts = posts[offset:offset + per_page]

        current_user = request.user if request.user.is_authenticated else None

        return JsonResponse({
            'posts': [_serialize_post(p, current_user) for p in posts],
            'total': total,
            'page': page,
            'per_page': per_page,
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def get_post(request, post_id):
    """Get a single post with comments."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        post = get_object_or_404(Post, id=post_id)
        current_user = request.user if request.user.is_authenticated else None
        comments = post.comments.select_related('author').all()

        return JsonResponse({
            'post': _serialize_post(post, current_user),
            'comments': [_serialize_comment(c) for c in comments],
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def delete_post(request, post_id):
    """Delete a post (author only)."""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    post = get_object_or_404(Post, id=post_id)
    if post.author != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    post.delete()
    return JsonResponse({'message': 'Post deleted'})


@csrf_exempt
def toggle_like(request, post_id):
    """Like or unlike a post."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    post = get_object_or_404(Post, id=post_id)
    like, created = PostLike.objects.get_or_create(user=request.user, post=post)

    if not created:
        like.delete()
        liked = False
    else:
        liked = True

    return JsonResponse({
        'liked': liked,
        'like_count': post.likes.count(),
    })


@csrf_exempt
def add_comment(request, post_id):
    """Add a comment to a post."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        data = json.loads(request.body)
        content = data.get('content', '').strip()
        if not content:
            return JsonResponse({'error': 'Comment content is required'}, status=400)

        post = get_object_or_404(Post, id=post_id)
        comment = Comment.objects.create(
            author=request.user,
            post=post,
            content=content,
        )

        return JsonResponse({
            'message': 'Comment added',
            'comment': _serialize_comment(comment),
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def delete_comment(request, comment_id):
    """Delete a comment (author only)."""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    comment = get_object_or_404(Comment, id=comment_id)
    if comment.author != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    comment.delete()
    return JsonResponse({'message': 'Comment deleted'})


# =============================================================================
# Group Views
# =============================================================================

@csrf_exempt
def list_groups(request):
    """List all groups or search groups."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        query = request.GET.get('q', '').strip()
        groups = Group.objects.all()
        if query:
            groups = groups.filter(
                Q(name__icontains=query) | Q(description__icontains=query)
            )

        current_user = request.user if request.user.is_authenticated else None

        results = []
        for g in groups:
            membership = None
            if current_user:
                try:
                    m = GroupMembership.objects.get(user=current_user, group=g)
                    membership = {'role': m.role, 'status': m.status}
                except GroupMembership.DoesNotExist:
                    pass

            results.append({
                'id': g.id,
                'name': g.name,
                'description': g.description,
                'created_by': {
                    'id': g.created_by.id,
                    'username': g.created_by.username,
                },
                'member_count': g.member_count,
                'membership': membership,
                'created_at': g.created_at.isoformat(),
            })

        return JsonResponse({'groups': results})

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def create_group(request):
    """Create a new group."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()

        if not name:
            return JsonResponse({'error': 'Group name is required'}, status=400)

        if Group.objects.filter(name__iexact=name).exists():
            return JsonResponse({'error': 'A group with this name already exists'}, status=400)

        group = Group.objects.create(
            name=name,
            description=description,
            created_by=request.user,
        )

        # Creator automatically joins as admin
        GroupMembership.objects.create(
            user=request.user,
            group=group,
            role='admin',
            status='active',
        )

        return JsonResponse({
            'message': 'Group created successfully',
            'group': {
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'member_count': 1,
                'created_at': group.created_at.isoformat(),
            }
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def get_group_detail(request, group_id):
    """Get group details and members."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        group = get_object_or_404(Group, id=group_id)
        memberships = group.memberships.filter(status='active').select_related('user')

        current_user = request.user if request.user.is_authenticated else None
        my_membership = None
        if current_user:
            try:
                m = GroupMembership.objects.get(user=current_user, group=group)
                my_membership = {'role': m.role, 'status': m.status}
            except GroupMembership.DoesNotExist:
                pass

        from form.models import UserProfile
        members = []
        for m in memberships:
            try:
                profile = UserProfile.objects.get(user=m.user)
                pic_url = profile.profile_picture.url if profile.profile_picture else None
            except UserProfile.DoesNotExist:
                pic_url = None
            members.append({
                'id': m.user.id,
                'username': m.user.username,
                'role': m.role,
                'profile_picture_url': pic_url,
                'joined_at': m.joined_at.isoformat(),
            })

        return JsonResponse({
            'group': {
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'created_by': {
                    'id': group.created_by.id,
                    'username': group.created_by.username,
                },
                'member_count': group.member_count,
                'my_membership': my_membership,
                'created_at': group.created_at.isoformat(),
            },
            'members': members,
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def join_group(request, group_id):
    """Join a group."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    group = get_object_or_404(Group, id=group_id)

    membership, created = GroupMembership.objects.get_or_create(
        user=request.user,
        group=group,
        defaults={'role': 'member', 'status': 'active'},
    )

    if not created:
        if membership.status == 'banned':
            return JsonResponse({'error': 'You are banned from this group'}, status=403)
        if membership.status == 'active':
            return JsonResponse({'message': 'Already a member'})
        membership.status = 'active'
        membership.save()

    return JsonResponse({
        'message': 'Joined group successfully',
        'member_count': group.member_count,
    })


@csrf_exempt
def leave_group(request, group_id):
    """Leave a group."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    group = get_object_or_404(Group, id=group_id)

    try:
        membership = GroupMembership.objects.get(user=request.user, group=group)
        if membership.role == 'admin' and group.memberships.filter(role='admin', status='active').count() <= 1:
            return JsonResponse({'error': 'Cannot leave: you are the only admin'}, status=400)
        membership.delete()
        return JsonResponse({
            'message': 'Left group successfully',
            'member_count': group.member_count,
        })
    except GroupMembership.DoesNotExist:
        return JsonResponse({'error': 'Not a member of this group'}, status=400)


@csrf_exempt
def add_member_to_group(request, group_id):
    """Add a user to a group (admin/moderator only)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    group = get_object_or_404(Group, id=group_id)

    # Check that requester is admin or moderator
    try:
        requester_membership = GroupMembership.objects.get(
            user=request.user, group=group, status='active'
        )
        if requester_membership.role not in ('admin', 'moderator'):
            return JsonResponse({'error': 'Only admins and moderators can add members'}, status=403)
    except GroupMembership.DoesNotExist:
        return JsonResponse({'error': 'You are not a member of this group'}, status=403)

    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        if not user_id:
            return JsonResponse({'error': 'user_id is required'}, status=400)

        target_user = get_object_or_404(User, id=user_id)

        membership, created = GroupMembership.objects.get_or_create(
            user=target_user,
            group=group,
            defaults={'role': 'member', 'status': 'active'},
        )

        if not created:
            if membership.status == 'active':
                return JsonResponse({'message': f'{target_user.username} is already a member'})
            membership.status = 'active'
            membership.save()

        from form.models import UserProfile
        try:
            profile = UserProfile.objects.get(user=target_user)
            pic_url = profile.profile_picture.url if profile.profile_picture else None
        except UserProfile.DoesNotExist:
            pic_url = None

        return JsonResponse({
            'message': f'{target_user.username} added to group',
            'member': {
                'id': target_user.id,
                'username': target_user.username,
                'role': membership.role,
                'profile_picture_url': pic_url,
                'joined_at': membership.joined_at.isoformat(),
            },
            'member_count': group.member_count,
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def remove_member_from_group(request, group_id, user_id):
    """Remove a user from a group (admin only)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    group = get_object_or_404(Group, id=group_id)

    # Check that requester is admin
    try:
        requester_membership = GroupMembership.objects.get(
            user=request.user, group=group, status='active'
        )
        if requester_membership.role != 'admin':
            return JsonResponse({'error': 'Only admins can remove members'}, status=403)
    except GroupMembership.DoesNotExist:
        return JsonResponse({'error': 'You are not a member of this group'}, status=403)

    target_user = get_object_or_404(User, id=user_id)

    if target_user == request.user:
        return JsonResponse({'error': 'Cannot remove yourself. Use leave group instead.'}, status=400)

    try:
        membership = GroupMembership.objects.get(user=target_user, group=group)
        membership.delete()
        return JsonResponse({
            'message': f'{target_user.username} removed from group',
            'member_count': group.member_count,
        })
    except GroupMembership.DoesNotExist:
        return JsonResponse({'error': 'User is not a member of this group'}, status=400)