"""DRF API views for the account app v2."""
from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from account import views as v1_views
from account.util import convert_param_to_int
from api import serializers
from api.authentication import ThreeScaleAuthentication
from api.models import CloudAccount, Instance, MachineImage


class AccountViewSet(mixins.CreateModelMixin,
                     mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin,
                     mixins.ListModelMixin,
                     mixins.DestroyModelMixin,
                     viewsets.GenericViewSet):
    """
    Create, retrieve, update, delete, or list customer accounts.

    Authenticate via 3scale.
    """

    authentication_classes = (ThreeScaleAuthentication, )
    serializer_class = serializers.CloudAccountSerializer
    queryset = CloudAccount.objects.all()

    def get_queryset(self):
        """Get the queryset filtered to appropriate user."""
        user = self.request.user
        if not user.is_superuser:
            return self.queryset.filter(user=user)
        user_id = self.request.query_params.get('user_id', None)
        if user_id is not None:
            user_id = convert_param_to_int('user_id', user_id)
            return self.queryset.filter(user__id=user_id)
        return self.queryset


class InstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List all or retrieve a single instance.

    Authenticate via 3scale.
    Do not allow to create, update, replace, or delete an instance at
    this view because we currently **only** allow instances to be retrieved.
    """

    authentication_classes = (ThreeScaleAuthentication, )
    serializer_class = serializers.InstanceSerializer
    queryset = Instance.objects.all()

    def get_queryset(self):
        """Filter the queryset."""
        # Filter to the appropriate user
        user = self.request.user
        if not user.is_superuser:
            self.queryset = self.queryset.filter(
                cloud_account__user__id=user.id)
        user_id = self.request.query_params.get('user_id', None)
        if user_id is not None:
            user_id = convert_param_to_int('user_id', user_id)
            self.queryset = self.queryset.filter(
                cloud_account__user__id=user_id)

        # Filter based on the instance running
        running = self.request.query_params.get('running', None)
        if running is not None:
            self.queryset = self.queryset.prefetch_related('run_set')
            if running.lower() == 'true':
                # The query for run!=None is needed because Django constructs
                # the query with LEFT OUTER JOIN, so if an run doesn't exist,
                # the instance is still in the queryset.
                # The discussion for this problem can be found:
                # https://gitlab.com/cloudigrade/cloudigrade/merge_requests/593#note_154802463  # noqa: E501
                # TODO: improve performance by forcing Django to INNER JOIN

                # truthiness table:
                # has endtime  |   run exists   |   include
                # T            |   T            |   F
                # T            |   F            |   F (will not happen IRL)
                # F            |   T            |   T
                # F            |   F            |   F
                self.queryset = self.queryset.filter(
                    Q(run__end_time=None) &
                    ~Q(run=None)
                ).distinct()
            elif running.lower() == 'false':
                # truthiness table:
                # has endtime  |   run exists   |   include
                # T            |   T            |   T
                # T            |   F            |   T (will not happen IRL)
                # F            |   T            |   F
                # F            |   F            |   T
                self.queryset = self.queryset.filter(
                    ~Q(run__end_time=None) |
                    Q(run=None)
                ).distinct()

        return self.queryset


class MachineImageViewSet(viewsets.ReadOnlyModelViewSet,
                          mixins.UpdateModelMixin):
    """
    List all, retrieve, or update a single machine image.

    Authenticate via 3scale.
    """

    authentication_classes = (ThreeScaleAuthentication, )
    serializer_class = serializers.MachineImageSerializer
    queryset = MachineImage.objects.all()

    def get_queryset(self):
        """
        Get the queryset of MachineImages filtered to appropriate user.

        Superusers by default see *all* objects unfiltered, but a superuser may
        optionally provide a `user_id` argument in order to see what that user
        would normally see. This argument is ignored for normal users.

        Because users don't necessarily own the images they have been using, we
        have the filter join across instanceevent to instance to account so
        that we return the set of images that any of their instances have used.

        If we ever support archiving activity from specific accounts or
        instances, we will need to expand the conditions on this filter to
        exclude images used by archived instances (via archived accounts).
        """
        user = self.request.user
        if not user.is_superuser:
            return self.queryset.filter(
                instance__cloud_account__user_id=user.id
            ).order_by('id').distinct()
        user_id = self.request.query_params.get('user_id', None)
        if user_id is not None:
            user_id = convert_param_to_int('user_id', user_id)
            return self.queryset.filter(
                instance__cloud_account__user_id=user_id
            ).order_by('id').distinct()
        return self.queryset.order_by('id')

    @action(detail=True, methods=['post'])
    def reinspect(self, request, pk=None):
        """Set the machine image status to pending, so it gets reinspected."""
        user = self.request.user

        if not user.is_superuser:
            return Response(status=status.HTTP_403_FORBIDDEN)

        machine_image = self.get_object()
        machine_image.status = MachineImage.PENDING
        machine_image.save()

        serializer = serializers.MachineImageSerializer(
            machine_image,
            context={'request': request}
        )

        return Response(serializer.data)


class SysconfigViewSet(v1_views.SysconfigViewSet):
    """
    View to display our cloud account ids.

    Authenticate via 3scale.
    """

    authentication_classes = (ThreeScaleAuthentication, )
