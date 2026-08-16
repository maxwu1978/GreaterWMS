from django.urls import path

from .views import TenantCleanupPreviewView, TenantCleanupView


urlpatterns = [
    path('cleanup/preview/', TenantCleanupPreviewView.as_view(), name='tenant-cleanup-preview'),
    path('cleanup/', TenantCleanupView.as_view(), name='tenant-cleanup'),
]
