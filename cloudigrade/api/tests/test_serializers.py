"""Collection of tests for custom DRF serializers in the account app."""
from unittest.mock import Mock, patch

import faker
from django.test import TestCase, TransactionTestCase

from api.models import (AwsCloudAccount,
                        AwsMachineImage, CloudAccount, Instance)
from api.serializers import (CloudAccountSerializer,
                             MachineImageSerializer, aws)
from util.tests import helper as util_helper

_faker = faker.Faker()


class AwsAccountSerializerTest(TransactionTestCase):
    """AwsAccount serializer test case."""

    def setUp(self):
        """Set up shared test data."""
        self.aws_account_id = util_helper.generate_dummy_aws_account_id()
        self.arn = util_helper.generate_dummy_arn(self.aws_account_id)
        self.role = util_helper.generate_dummy_role()
        self.validated_data = {
            'account_arn': self.arn,
            'name': 'account_name',
            'cloud_type': 'aws',
        }

    def test_serialization_fails_on_empty_account_name(self):
        """Test that an account is not saved if verification fails."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        validated_data = {
            'account_arn': self.arn,
        }

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_verify.return_value = True, []

            serializer = CloudAccountSerializer(
                context=context,
                data=validated_data
            )
            serializer.is_valid()
            self.assertEquals('This field is required.',
                              str(serializer.errors['name'][0]))

    def test_create_succeeds_when_account_verified(self):
        """Test saving of a test ARN."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        serializer = CloudAccountSerializer(context=context)

        result = serializer.create(self.validated_data)
        self.assertIsInstance(result, CloudAccount)

        # Verify that we created the account.
        account = AwsCloudAccount.objects.get(
            aws_account_id=self.aws_account_id)
        self.assertEqual(self.aws_account_id, account.aws_account_id)
        self.assertEqual(self.arn, account.account_arn)

        # Verify that we created no instances yet.
        instances = Instance.objects.filter(
            cloud_account=account.cloud_account.get()).all()
        self.assertEqual(len(instances), 0)

        # Verify that we created no images yet.
        amis = AwsMachineImage.objects.all()
        self.assertEqual(len(amis), 0)


class AwsMachineImageSerializerTest(TestCase):
    """AwsMachineImage serializer test case."""

    def test_update_succeeds_when_rhel_challenged_is_unset(self):
        """If RHEL challenged is unset, test that the update succeeds."""
        mock_image = Mock()
        mock_image.rhel_challenged = True
        mock_image.openshift_challenged = True
        mock_image.save = Mock(return_value=None)
        validated_data = {
            'rhel_challenged': False
        }
        serializer = MachineImageSerializer()
        serializer.update(mock_image, validated_data)
        self.assertFalse(mock_image.rhel_challenged)
        mock_image.save.assert_called()

    def test_update_succeeds_when_rhel_challenged_is_set(self):
        """If RHEL challenged is set, test that the update succeeds."""
        mock_image = Mock()
        mock_image.rhel_challenged = False
        mock_image.openshift_challenged = True
        mock_image.save = Mock(return_value=None)

        validated_data = {
            'rhel_challenged': True
        }
        serializer = MachineImageSerializer()
        serializer.update(mock_image, validated_data)
        self.assertTrue(mock_image.rhel_challenged)

    def test_no_update_when_nothing_changes(self):
        """If RHEL challenged is set, test that the update succeeds."""
        mock_image = Mock()
        mock_image.rhel_challenged = False
        mock_image.openshift_challenged = False
        mock_image.save = Mock(return_value=None)

        validated_data = {}

        serializer = MachineImageSerializer()
        serializer.update(mock_image, validated_data)

        self.assertFalse(mock_image.rhel_challenged)
        self.assertFalse(mock_image.openshift_challenged)
        mock_image.save.assert_not_called()
