from django.urls import path
from . import views

app_name = 'community'

urlpatterns = [
    # Community & Sharing (Sprint 9)
    path('matches/', views.find_potential_matches, name='find_matches'),
    path('matches/<int:match_id>/confirm/', views.confirm_ancestor_match, name='confirm_match'),
    path('tree/merged/', views.get_merged_family_tree, name='merged_tree'),

    # Direct Family Connections (Friendships)
    path('connections/', views.list_connections, name='list_connections'),
    path('connections/request/<int:user_id>/', views.send_connection_request, name='send_connection_request'),
    path('connections/accept/<int:connection_id>/', views.accept_connection_request, name='accept_connection_request'),

    # Social Media - Posts
    path('posts/', views.list_posts, name='list_posts'),
    path('posts/create/', views.create_post, name='create_post'),
    path('posts/<int:post_id>/', views.get_post, name='get_post'),
    path('posts/<int:post_id>/delete/', views.delete_post, name='delete_post'),
    path('posts/<int:post_id>/like/', views.toggle_like, name='toggle_like'),
    path('posts/<int:post_id>/comments/', views.add_comment, name='add_comment'),
    path('comments/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),

    # User search (for tagging and connecting)
    path('users/search/', views.search_users, name='search_users'),

    # Groups
    path('groups/', views.list_groups, name='list_groups'),
    path('groups/create/', views.create_group, name='create_group'),
    path('groups/<int:group_id>/', views.get_group_detail, name='group_detail'),
    path('groups/<int:group_id>/join/', views.join_group, name='join_group'),
    path('groups/<int:group_id>/leave/', views.leave_group, name='leave_group'),
    path('groups/<int:group_id>/add-member/', views.add_member_to_group, name='add_member'),
    path('groups/<int:group_id>/remove-member/<int:user_id>/', views.remove_member_from_group, name='remove_member'),
]