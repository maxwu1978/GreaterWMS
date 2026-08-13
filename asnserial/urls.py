from django.urls import path

from . import views


urlpatterns = [
    path('records/', views.SerialRecordsView.as_view(), name='asn-serial-records'),
    path('exceptions/', views.SerialExceptionsView.as_view(), name='asn-serial-exceptions'),
    path('exceptions/resolve/', views.SerialExceptionResolveView.as_view(), name='asn-serial-exception-resolve'),
    path('exceptions/move/', views.SerialExceptionMoveView.as_view(), name='asn-serial-exception-move'),
    path('exceptions/resolve-quantity/', views.QuantityExceptionResolveView.as_view(), name='asn-quantity-exception-resolve'),
    path('exceptions/move-quantity/', views.QuantityExceptionMoveView.as_view(), name='asn-quantity-exception-move'),
    path('summary/', views.SerialSummaryView.as_view(), name='asn-serial-summary'),
    path('expected/', views.ExpectedSerialView.as_view(), name='asn-serial-expected'),
    path('scan/', views.ScanSerialView.as_view(), name='asn-serial-scan'),
    path('packlists/', views.PackListListView.as_view(), name='asn-pack-list-list'),
    path('packlists/create/', views.PackListCreateView.as_view(), name='asn-pack-list-create'),
    path('packlists/preview/', views.PackListPreviewView.as_view(), name='asn-pack-list-preview'),
    path('packlists/import/', views.PackListImportView.as_view(), name='asn-pack-list-import'),
    path('packlists/confirm/', views.PackListConfirmView.as_view(), name='asn-pack-list-confirm'),
    path('import/', views.SerialImportView.as_view(), name='asn-serial-import'),
    path('inspections/import/', views.SerialImportView.as_view(), {'inspection': True}, name='asn-serial-inspection-import'),
    path('inspections/preview/', views.SerialImportPreviewView.as_view(), {'inspection': True}, name='asn-serial-inspection-preview'),
    path('import/preview/', views.SerialImportPreviewView.as_view(), name='asn-serial-import-preview'),
    path('inspections/', views.InspectionBatchListView.as_view(), name='asn-serial-inspection-list'),
    path('agent/preview/', views.AgentCommandPreviewView.as_view(), name='asn-agent-command-preview'),
]
