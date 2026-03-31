from django.db import models
from django.contrib.auth.models import User

# Import the new Person model from heritage
from heritage.models import Person

class FamilyConnection(models.Model):
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='family_connections_initiated')
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='family_connections_received')
    connection_type = models.CharField(max_length=50)
    confidence_score = models.FloatField()
    shared_ancestor_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('rejected', 'Rejected')], default='pending')

class AncestorMatch(models.Model):
    # Updated to link to the new Person table
    person1 = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='matches_as_first')
    person2 = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='matches_as_second')
    confidence_score = models.FloatField()
    matching_attributes = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=[('suggested', 'Suggested'), ('confirmed', 'Confirmed'), ('rejected', 'Rejected')], default='suggested')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)


# =============================================================================
# Social Media & Group Models
# =============================================================================

def upload_post_image_path(instance, filename):
    """Generate upload path for post images."""
    ext = filename.split('.')[-1]
    filename = f'post_{uuid.uuid4()}.{ext}'
    return f'media/posts/{filename}'


class Post(models.Model):
    """A social media post that can tag other users."""
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='posts')
    content = models.TextField(max_length=2000)
    image = models.ImageField(upload_to=upload_post_image_path, null=True, blank=True)
    tagged_users = models.ManyToManyField(User, related_name='tagged_in_posts', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Post by {self.author.username} at {self.created_at}"


class PostLike(models.Model):
    """A like on a post."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='post_likes')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post')

    def __str__(self):
        return f"{self.user.username} likes post {self.post.id}"


class Comment(models.Model):
    """A comment on a post."""
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    content = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author.username} on post {self.post.id}"


class Group(models.Model):
    """A community group that users can join."""
    name = models.CharField(max_length=200)
    description = models.TextField(max_length=1000, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_groups')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def member_count(self):
        return self.memberships.filter(status='active').count()


class GroupMembership(models.Model):
    """Tracks user membership in groups."""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('pending', 'Pending'),
        ('banned', 'Banned'),
    ]
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('moderator', 'Moderator'),
        ('member', 'Member'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='group_memberships')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'group')

    def __str__(self):
        return f"{self.user.username} in {self.group.name}"


class GroupPost(models.Model):
    """A post made within a group."""
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='group_posts')
    post = models.OneToOneField(Post, on_delete=models.CASCADE, related_name='group_context')

    def __str__(self):
        return f"Post in {self.group.name} by {self.post.author.username}"
