"""Cloudigrade URL Configuration."""
from django.conf.urls import url
from django.contrib import admin
from django.urls import include, path
from rest_framework import routers

from account.v2.views import SysconfigViewSetV2
from account.views import (AccountViewSet,
                           CloudAccountOverviewViewSet,
                           DailyInstanceActivityViewSet,
                           ImagesActivityOverviewViewSet,
                           InstanceEventViewSet,
                           InstanceViewSet,
                           MachineImageViewSet,
                           SysconfigViewSet,
                           UserViewSet)

router = routers.DefaultRouter()
router.register(r'account', AccountViewSet)
router.register(r'event', InstanceEventViewSet)
router.register(r'instance', InstanceViewSet)
router.register(r'image', MachineImageViewSet)
router.register(r'sysconfig', SysconfigViewSet, base_name='sysconfig')
router.register(r'report/accounts', CloudAccountOverviewViewSet,
                base_name='report-accounts')
router.register(r'user', UserViewSet, base_name='user')
router.register(r'report/images', ImagesActivityOverviewViewSet,
                base_name='report-images')
router.register(r'report/instances', DailyInstanceActivityViewSet,
                base_name='report-instances')

routerv2 = routers.DefaultRouter()
routerv2.register(r'sysconfig', SysconfigViewSetV2, base_name='sysconfig')

urlpatterns = [
    url(r'^api/v1/', include(router.urls)),
    url(r'^api/v2/', include(routerv2.urls)),
    url(r'^api-auth/', include('rest_framework.urls')),
    url(r'^healthz/', include('health_check.urls')),
    url(r'^auth/', include('dj_auth.urls')),
    url(r'^auth/', include('dj_auth.urls.authtoken')),
    path('admin/', admin.site.urls),
]
