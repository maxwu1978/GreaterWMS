from django.urls import path

from .views import StagingAssignmentsView, StagingReleaseView, StagingSlotsView


urlpatterns = [
    path('slots/', StagingSlotsView.as_view(), name='staging-slots'),
    path('assignments/', StagingAssignmentsView.as_view(), name='staging-assignments'),
    path('release/', StagingReleaseView.as_view(), name='staging-release'),
]
