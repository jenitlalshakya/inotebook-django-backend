from django.urls import path
from .views import signup, login, delete_account

urlpatterns = [
    path('auth/signup/', signup, name='signup'),
    path('auth/login/', login, name='login'),
    path('auth/delete_account/', delete_account, name='delete_account'),
]
