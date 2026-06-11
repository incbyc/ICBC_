from django.urls import path

from .views import GlobalSummaryView, ICBCSiteDetailView

urlpatterns = [
    path("sites/<slug:slug>/", ICBCSiteDetailView.as_view(), name="icbc-site-detail"),
    path("summary/", GlobalSummaryView.as_view(), name="icbc-global-summary"),
]

