from django.urls import path
from . import views

urlpatterns = [
    path('upload', views.upload_file, name='upload-file'),
    path('list', views.list_files, name='list-files'),
    path('delete/<str:file_id>', views.delete_file, name='delete-file'),
]
