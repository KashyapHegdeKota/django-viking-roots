from django.contrib import admin
from .models import (
    FamilyConnection, AncestorMatch, MergedFamilyTree,
    Post, PostLike, Comment, Group, GroupMembership, GroupPost,
)

admin.site.register(FamilyConnection)
admin.site.register(AncestorMatch)
admin.site.register(MergedFamilyTree)
admin.site.register(Post)
admin.site.register(PostLike)
admin.site.register(Comment)
admin.site.register(Group)
admin.site.register(GroupMembership)
admin.site.register(GroupPost)
