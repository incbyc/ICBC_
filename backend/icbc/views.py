from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ICBCSite
from .serializers import GlobalSummarySerializer, ICBCSiteDetailSerializer


class ICBCSiteDetailView(generics.RetrieveAPIView):
    """Read-only API for a single ICBC site with stats & updates."""

    lookup_field = "slug"
    queryset = ICBCSite.objects.all().prefetch_related(
        "pastor",
        "images",
        "updates",
        "weekly_stats",
    )
    serializer_class = ICBCSiteDetailSerializer


class GlobalSummaryView(APIView):
    """Aggregate summary across all ICBC sites for the CMS overview page."""

    def get(self, request, *args, **kwargs):
        serializer = GlobalSummarySerializer.from_db()
        return Response(serializer.data)

