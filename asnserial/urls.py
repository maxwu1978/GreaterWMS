from django.urls import path

from . import views


urlpatterns = [
    path('records/', views.SerialRecordsView.as_view(), name='asn-serial-records'),
    path('summary/', views.SerialSummaryView.as_view(), name='asn-serial-summary'),
    path('expected/', views.ExpectedSerialView.as_view(), name='asn-serial-expected'),
    path('scan/', views.ScanSerialView.as_view(), name='asn-serial-scan'),
    path('packlists/', views.PackListListView.as_view(), name='asn-pack-list-list'),
    path('packlists/create/', views.PackListCreateView.as_view(), name='asn-pack-list-create'),
    path('packlists/import/', views.PackListImportView.as_view(), name='asn-pack-list-import'),
    path('packlists/confirm/', views.PackListConfirmView.as_view(), name='asn-pack-list-confirm'),
    path('import/', views.SerialImportView.as_view(), name='asn-serial-import'),
]
