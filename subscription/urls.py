from django.urls import path
from . import views

urlpatterns = [
    path('configs', views.configs, name='subscription-configs'),
    path('payment/', views.initiate_payment, name='initiate-payment'),
    path('success', views.payment_success, name='payment-success'),
    path('failure', views.payment_failure, name='payment-failure'),
]
