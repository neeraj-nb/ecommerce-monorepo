"""product_service URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from products.views import ProductViewSet, ReviewViewSet
from rest_framework_nested.routers import NestedDefaultRouter

# Product routes
router = DefaultRouter()
router.register('products', ProductViewSet, basename='product')

# Nested review routes
product_router = NestedDefaultRouter(router, 'products', lookup='product')
product_router.register('reviews', ReviewViewSet, basename='product-reviews')

urlpatterns = [
    path('admin/', admin.site.urls),
    # path('api/', include('app.urls')),
    path('', include('health.urls')),
    path('api/', include(router.urls)),
    path('api/', include(product_router.urls)),
]
