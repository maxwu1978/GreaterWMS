from django.urls import path

from . import views


urlpatterns = [
    path('records/', views.SerialRecordsView.as_view(), name='asn-serial-records'),
    path('summary/', views.SerialSummaryView.as_view(), name='asn-serial-summary'),
    path('expected/', views.ExpectedSerialView.as_view(), name='asn-serial-expected'),
    path('scan/', views.ScanSerialView.as_view(), name='asn-serial-scan'),
    path('import/', views.SerialImportView.as_view(), name='asn-serial-import'),
]
