"""Cloudigrade URL Configuration."""
from django.conf.urls import url
from django.contrib import admin
from django.urls import include, path
from rest_framework import permissions, renderers, routers
from rest_framework.schemas import get_schema_view

from api import views as public_views
from api.internal import views as internal_views

router = routers.DefaultRouter()
router.register(r"accounts", public_views.AccountViewSet, basename="v2-account")
router.register(r"instances", public_views.InstanceViewSet, basename="v2-instance")
router.register(r"images", public_views.MachineImageViewSet, basename="v2-machineimage")
router.register(r"sysconfig", public_views.SysconfigViewSet, basename="v2-sysconfig")
router.register(
    r"concurrent", public_views.DailyConcurrentUsageViewSet, basename="v2-concurrent"
)

public_urlpatterns = [
    url(r"^api/cloudigrade/v2/", include(router.urls)),
    path(
        "api/cloudigrade/v2/openapi.json",
        get_schema_view(
            title="Cloudigrade",
            renderer_classes=[
                renderers.JSONOpenAPIRenderer,
            ],
            permission_classes=[permissions.AllowAny],
            authentication_classes=[],
            public=True,
        ),
        name="openapi-schema",
    ),
]

internal_urlpatterns = [
    url(r"^internal/api-auth/", include("rest_framework.urls")),
    url(r"^internal/healthz/", include("health_check.urls")),
    path("internal/admin/", admin.site.urls),
    url(r"^internal/", include("django_prometheus.urls")),
]

internal_router = routers.DefaultRouter()
internal_router.register(
    r"users", internal_views.InternalUserViewSet, basename="internal-user"
)
internal_router.register(
    r"cloudaccounts",
    internal_views.InternalCloudAccountViewSet,
    basename="internal-cloudaccount",
)
internal_router.register(
    r"instances",
    internal_views.InternalInstanceViewSet,
    basename="internal-instance",
)
internal_router.register(
    r"instanceevents",
    internal_views.InternalInstanceEventViewSet,
    basename="internal-instanceevent",
)
internal_router.register(
    r"machineimages",
    internal_views.InternalMachineImageViewSet,
    basename="internal-machineimage",
)
internal_router.register(
    r"runs", internal_views.InternalRunViewSet, basename="internal-run"
)
internal_router.register(
    r"machineimageinspecitonstarts",
    internal_views.InternalMachineImageInspectionStartViewSet,
    basename="internal-machineimageinspecitonstart",
)
internal_router.register(
    r"concurrentusages",
    internal_views.InternalConcurrentUsageViewSet,
    basename="internal-concurrentusage",
)
internal_router.register(
    r"awscloudaccounts",
    internal_views.InternalAwsCloudAccountViewSet,
    basename="internal-awscloudaccount",
)
internal_router.register(
    r"awsinstances",
    internal_views.InternalAwsInstanceViewSet,
    basename="internal-awsinstance",
)
internal_router.register(
    r"awsmachineimages",
    internal_views.InternalAwsMachineImageViewSet,
    basename="internal-awsmachineimage",
)
internal_router.register(
    r"awsmachineimagecopies",
    internal_views.InternalAwsMachineImageCopyViewSet,
    basename="internal-awsmachineimagecopy",
)
internal_router.register(
    r"awsinstanceevents",
    internal_views.InternalAwsInstanceEventViewSet,
    basename="internal-awsinstanceevent",
)

internal_api_urlpatterns = [
    url(r"^internal/api/cloudigrade/v1/", include(internal_router.urls)),
    url(r"^internal/api/cloudigrade/v1/", internal_views.availability_check),
]

urlpatterns = public_urlpatterns + internal_urlpatterns + internal_api_urlpatterns
