from django.urls import path
from .views import create_note, get_notes, update_note, delete_note

urlpatterns = [
    path("create/", create_note),
    path("all/", get_notes),
    path("update/<str:note_id>/", update_note),
    path("delete/<str:note_id>/", delete_note),
]
