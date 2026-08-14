from django.urls import path

from . import views


urlpatterns = [
    path('orders/', views.TransportOrderListView.as_view(), name='transport-orders'),
    path('orders/<str:transport_no>/', views.TransportOrderDetailView.as_view(), name='transport-order-detail'),
    path('assign/', views.TransportAssignView.as_view(), name='transport-assign'),
    path('transition/', views.TransportTransitionView.as_view(), name='transport-transition'),
]
