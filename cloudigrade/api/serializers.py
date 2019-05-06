"""DRF API serializers for the account app v2."""
from django.utils.translation import gettext as _
from generic_relations.relations import GenericRelatedField
from rest_framework.exceptions import ValidationError
from rest_framework.fields import BooleanField, CharField, ChoiceField
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework.serializers import ModelSerializer

from api.models import (AwsCloudAccount, AwsInstance,
                        AwsMachineImage, CloudAccount, Instance,
                        MachineImage)
from util import aws
from util.exceptions import InvalidArn


class AwsCloudAccountSerializer(ModelSerializer):
    """Serialize a customer AWS CloudAccount for API v2."""

    class Meta:
        model = AwsCloudAccount
        fields = (
            'account_arn',
            'aws_account_id',
            'created_at',
            'id',
            'updated_at',
        )

    def validate_account_arn(self, value):
        """Validate the input account_arn."""
        if self.instance is not None and value != self.instance.account_arn:
            raise ValidationError(
                _('You cannot change this field.')
            )
        try:
            aws.AwsArn(value)
        except InvalidArn:
            raise ValidationError(
                _('Invalid ARN.')
            )
        return value


class CloudAccountSerializer(ModelSerializer):
    """Serialize a customer CloudAccount for API v2."""

    account_arn = CharField(required=False)
    aws_account_id = CharField(required=False)

    cloud_type = ChoiceField(
        choices=['aws', 'gcp', 'azure'],
        required=False
    )
    content_object = GenericRelatedField({
        AwsCloudAccount: AwsCloudAccountSerializer(),
    }, required=False)

    class Meta:
        model = CloudAccount
        fields = (
            'created_at',
            'id',
            'name',
            'updated_at',
            'user_id',
            'content_object',
            'cloud_type',
            'account_arn',
            'aws_account_id',
        )
        read_only_fields = (
            'aws_account_id',
            'user_id',
            'content_object',
        )

    def validate(self, data):
        """Validate that clount name is unique per user."""
        user = self.context['request'].user
        name = data.get('name')

        try:
            CloudAccount.objects.get(user=user, name=name)
        except CloudAccount.DoesNotExist:
            return data

        raise ValidationError(_(
            "Account with name '{0}' for user '{1}' already exists").format(
            name, user))

    def validate_account_arn(self, value):
        """Validate the input account_arn."""
        if self.instance is not None and value != \
                self.instance.content_object.account_arn:
            raise ValidationError(
                _('You cannot change this field.')
            )
        try:
            aws.AwsArn(value)
        except InvalidArn:
            raise ValidationError(
                _('Invalid ARN.')
            )
        return value

    def create(self, validated_data):
        """Create a CloudAccount."""
        cloud_type = validated_data['cloud_type']

        if cloud_type == 'aws':
            return self.create_aws_cloud_account(validated_data)
        elif cloud_type == 'gcp':
            return NotImplementedError
        elif cloud_type == 'azure':
            return NotImplementedError
        else:
            return NotImplementedError

    def update(self, instance, validated_data):
        """Update the instance with the name from validated_data."""
        instance.name = validated_data.get('name', instance.name)
        instance.save()
        return instance

    def get_user_id(self, account):
        """Get the user_id property for serialization."""
        return account.user_id

    def create_aws_cloud_account(self, validated_data):
        """Create an AWS flavored CloudAccount."""
        arn = aws.AwsArn(validated_data['account_arn'])
        aws_account_id = arn.account_id

        account_exists = AwsCloudAccount.objects.filter(
            aws_account_id=aws_account_id
        ).exists()
        if account_exists:
            raise ValidationError(
                detail={
                    'account_arn': [
                        _('An ARN already exists for account "{0}"').format(
                            aws_account_id
                        )
                    ]
                }
            )

        user = self.context['request'].user
        name = validated_data.get('name')
        aws_cloud_account = AwsCloudAccount(
            account_arn=str(arn),
            aws_account_id=aws_account_id,
        )
        aws_cloud_account.save()
        cloud_account = CloudAccount(
            name=name,
            user=user,
            content_object=aws_cloud_account
        )
        cloud_account.save()

        return cloud_account


class AwsMachineImageSerializer(ModelSerializer):
    """Serialize a customer AwsMachineImage for API v2."""

    class Meta:
        model = AwsMachineImage
        fields = (
            'created_at',
            'ec2_ami_id',
            'id',
            'owner_aws_account_id',
            'platform',
            'region',
            'updated_at',
            'is_cloud_access',
            'is_marketplace',
        )
        read_only_fields = (
            'created_at',
            'ec2_ami_id',
            'id',
            'owner_aws_account_id',
            'platform',
            'region',
            'updated_at',
            'is_cloud_access',
            'is_marketplace',
        )

    def create(self, validated_data):
        """Create an AwsMachineImage."""
        return NotImplementedError

    def update(self, instance, validated_data):
        """Update an AwsMachineImage."""
        return NotImplementedError


class MachineImageSerializer(ModelSerializer):
    """Serialize a customer AwsMachineImage for API v2."""

    cloud_type = ChoiceField(
        choices=['aws', 'gcp', 'azure'],
        required=False
    )
    content_object = GenericRelatedField({
        AwsMachineImage: AwsMachineImageSerializer(),
    }, required=False)

    rhel_challenged = BooleanField(required=False)
    openshift_challenged = BooleanField(required=False)

    class Meta:
        model = MachineImage
        fields = (
            'created_at',
            'id',
            'inspection_json',
            'is_encrypted',
            'name',
            'openshift',
            'openshift_challenged',
            'openshift_detected',
            'rhel',
            'rhel_challenged',
            'rhel_detected',
            'rhel_enabled_repos_found',
            'rhel_product_certs_found',
            'rhel_release_files_found',
            'rhel_signed_packages_found',
            'status',
            'updated_at',
            'cloud_type',
            'content_object',
        )
        read_only_fields = (
            'created_at',
            'id',
            'inspection_json',
            'is_encrypted',
            'name',
            'openshift',
            'openshift_detected',
            'rhel',
            'rhel_detected',
            'rhel_enabled_repos_found',
            'rhel_product_certs_found',
            'rhel_release_files_found',
            'rhel_signed_packages_found',
            'status',
            'updated_at',
            'cloud_type',
        )

    def update(self, image, validated_data):
        """
        Update the AwsMachineImage challenge properties.

        Args:
            image (MachineImage): Image to be updated.
            validated_data (dict): Dictionary of properties to be updated.

        Returns (AwsMachineImage): Updated object.

        """
        rhel_challenged = validated_data.get('rhel_challenged', None)
        openshift_challenged = validated_data.get('openshift_challenged', None)

        if rhel_challenged is not None:
            image.rhel_challenged = rhel_challenged

        if openshift_challenged is not None:
            image.openshift_challenged = openshift_challenged

        if rhel_challenged is not None or openshift_challenged is not None:
            image.save()

        return image


class AwsInstanceSerializer(ModelSerializer):
    """Serialize a customer AwsInstance for API v2."""

    class Meta:
        model = AwsInstance
        fields = (
            'created_at',
            'ec2_instance_id',
            'id',
            'region',
            'updated_at',
        )
        read_only_fields = (
            'account',
            'created_at',
            'ec2_instance_id',
            'id',
            'region',
            'updated_at',
        )

    def create(self, validated_data):
        """Create a AwsInstance."""
        return NotImplementedError

    def update(self, instance, validated_data):
        """Update a AwsInstance."""
        return NotImplementedError


class InstanceSerializer(ModelSerializer):
    """Serialize a customer AwsInstance for API v2."""

    cloud_type = ChoiceField(
        choices=['aws', 'gcp', 'azure'],
        required=False
    )
    content_object = GenericRelatedField({
        AwsInstance: AwsInstanceSerializer(),
    }, required=False)
    cloud_account = HyperlinkedIdentityField(view_name='v2-account-detail')
    machine_image = HyperlinkedIdentityField(
        view_name='v2-machineimage-detail')

    class Meta:
        model = Instance
        fields = (
            'cloud_account',
            'cloud_account_id',
            'created_at',
            'id',
            'machine_image',
            'machine_image_id',
            'updated_at',
            'cloud_type',
            'content_object',
        )
        read_only_fields = (
            'cloud_account',
            'cloud_account_id',
            'created_at',
            'id',
            'machine_image',
            'machine_image_id',
            'updated_at',
        )

    def create(self, validated_data):
        """Create a Instance."""
        return NotImplementedError

    def update(self, instance, validated_data):
        """Update a Instance."""
        return NotImplementedError
