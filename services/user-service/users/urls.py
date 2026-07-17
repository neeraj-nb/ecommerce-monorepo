from django.urls import path
from .views import RegisterView, ProfileView, CustomTokenView, UserDetailView
from .auth import VerifyTokenView
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', CustomTokenView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('users/<int:pk>/', UserDetailView.as_view(), name='user-detail'),
    path('auth/verify/', VerifyTokenView.as_view(), name='verify-token'),
]