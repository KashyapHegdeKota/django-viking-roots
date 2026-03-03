from django.db import models
from django.contrib.auth.models import User
from heritage.models import Ancestor

class FamilyConnection(models.Model):
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='family_connections_initiated')
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='family_connections_received')
    connection_type = models.CharField(max_length=50)
    confidence_score = models.FloatField()
    shared_ancestor_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('rejected', 'Rejected')], default='pending')

class AncestorMatch(models.Model):
    ancestor1 = models.ForeignKey(Ancestor, on_delete=models.CASCADE, related_name='matches_as_first')
    ancestor2 = models.ForeignKey(Ancestor, on_delete=models.CASCADE, related_name='matches_as_second')
    confidence_score = models.FloatField()
    matching_attributes = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=[('suggested', 'Suggested'), ('confirmed', 'Confirmed'), ('rejected', 'Rejected')], default='suggested')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

class MergedFamilyTree(models.Model):
    name = models.CharField(max_length=200)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_trees')
    members = models.ManyToManyField(User, related_name='family_trees')