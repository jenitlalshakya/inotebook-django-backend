from django.urls import path
from .views import create_note, get_notes, search_notes, update_note, delete_note, permanent_delete_note, empty_trash, get_trash_notes, restore_note, favorite_note, unfavorite_note, get_favorites

urlpatterns = [
    path("create/", create_note),
    path("all/", get_notes),
    path("search/", search_notes),
    path("update/<str:note_id>/", update_note),
    path("delete/<str:note_id>/", delete_note),
    path("delete-permanent/<str:note_id>/", permanent_delete_note),
    path("empty-trash/", empty_trash),
    path("get-trash/", get_trash_notes),
    path("restore/<str:note_id>/", restore_note),
    path("favorite/<str:note_id>/", favorite_note),
    path("unfavorite/<str:note_id>/", unfavorite_note),
    path("favorites/", get_favorites),
]
