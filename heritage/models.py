from django.db import models
from django.contrib.auth.models import User

# ---------------------------------------------------------------------------
# The Access Layer (Shared Trees)
# ---------------------------------------------------------------------------

class FamilyTree(models.Model):
    """The container for a shared or individual family tree."""
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class TreeAccess(models.Model):
    """Manages which users can view or edit which trees."""
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('editor', 'Editor'),
        ('viewer', 'Viewer'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tree_access')
    tree = models.ForeignKey(FamilyTree, on_delete=models.CASCADE, related_name='access_rules')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='viewer')

    class Meta:
        unique_together = ('user', 'tree')

# ---------------------------------------------------------------------------
# The Details Layer (Places & Events)
# ---------------------------------------------------------------------------

class Location(models.Model):
    """Normalized locations to prevent database bloat."""
    name = models.CharField(max_length=255, unique=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    def __str__(self):
        return self.name

# ---------------------------------------------------------------------------
# The Entity Layer (Core Nodes)
# ---------------------------------------------------------------------------

class Person(models.Model):
    """Represents an individual (INDI)."""
    tree = models.ForeignKey(FamilyTree, on_delete=models.CASCADE, related_name='people')
    gedcom_id = models.CharField(max_length=50, blank=True, null=True) # e.g., I1
    first_name = models.CharField(max_length=255, blank=True)
    last_name = models.CharField(max_length=255, blank=True)
    gender = models.CharField(max_length=1, choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other'), ('U', 'Unknown')], default='U')
    
    # Quick-reference fields for the UI
    birth_year = models.IntegerField(null=True, blank=True)
    death_year = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip() or "Unknown Person"

class FamilyGroup(models.Model):
    """Represents a marriage/union (FAM)."""
    tree = models.ForeignKey(FamilyTree, on_delete=models.CASCADE, related_name='families')
    gedcom_id = models.CharField(max_length=50, blank=True, null=True) # e.g., F1
    husband = models.ForeignKey(Person, on_delete=models.SET_NULL, null=True, blank=True, related_name='families_as_husband')
    wife = models.ForeignKey(Person, on_delete=models.SET_NULL, null=True, blank=True, related_name='families_as_wife')

class ChildLink(models.Model):
    """Links a Person to a FamilyGroup as a child."""
    family = models.ForeignKey(FamilyGroup, on_delete=models.CASCADE, related_name='children_links')
    child = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='parent_family_links')
    rel_type = models.CharField(max_length=50, default='Biological') # e.g., Adopted, Step

    class Meta:
        unique_together = ('family', 'child')

class Event(models.Model):
    """Unified event table for births, deaths, marriages, etc."""
    tree = models.ForeignKey(FamilyTree, on_delete=models.CASCADE, related_name='events')
    person = models.ForeignKey(Person, on_delete=models.CASCADE, null=True, blank=True, related_name='events')
    family = models.ForeignKey(FamilyGroup, on_delete=models.CASCADE, null=True, blank=True, related_name='events')
    event_type = models.CharField(max_length=50) # e.g., BIRT, DEAT, MARR
    date_string = models.CharField(max_length=100, blank=True)
    parsed_date = models.DateField(null=True, blank=True)
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True)

class Fact(models.Model):
    """Stores extra extracted data or custom attributes."""
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='facts')
    key = models.CharField(max_length=100)
    value = models.TextField()

class Story(models.Model):
    """Stores AI-generated narratives about specific people."""
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='stories')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Story about {self.person}"