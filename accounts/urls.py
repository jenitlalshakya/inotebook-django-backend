from django.urls import path
from .views import signup, login, delete_account, change_password, profile

urlpatterns = [
    path('auth/signup/', signup, name='signup'),
    path('auth/login/', login, name='login'),
    path('auth/profile/', profile, name='profile'),
    path('auth/delete-account/', delete_account, name='delete-account'),
    path('auth/change-password/', change_password, name='change-password'),
]
