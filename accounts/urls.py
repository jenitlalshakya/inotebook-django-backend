from django.urls import path
from .views import signup, login, delete_account, change_password

urlpatterns = [
    path('auth/signup/', signup, name='signup'),
    path('auth/login/', login, name='login'),
    path('auth/delete-account/', delete_account, name='delete-account'),
    path('auth/change-password/', change_password, name='change-password'),
]
