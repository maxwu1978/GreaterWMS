from django.urls import path

from . import views


urlpatterns = [
    path('records/', views.ReceivingRecordListView.as_view(), name='receiving-records'),
    path('records/<int:pk>/', views.ReceivingRecordDetailView.as_view(), name='receiving-record-detail'),
    path('staging/assign/', views.ReceivingStagingAssignView.as_view(), name='receiving-staging-assign'),
    path('putaway/assign/', views.ReceivingPutawayAssignView.as_view(), name='receiving-putaway-assign'),
    path('qc/complete/', views.ReceivingQcCompleteView.as_view(), name='receiving-qc-complete'),
    path('exceptions/resolve/', views.ReceivingExceptionResolveView.as_view(), name='receiving-exception-resolve'),
    path('putaway/', views.ReceivingPutawayView.as_view(), name='receiving-putaway'),
    path('reconcile/', views.ReceivingReconcileView.as_view(), name='receiving-reconcile'),
    path('reconcile/resolve/', views.ReceivingReconcileResolveView.as_view(), name='receiving-reconcile-resolve'),
    path('exceptions/', views.ReceivingExceptionListView.as_view(), name='receiving-exceptions'),
]
