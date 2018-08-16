"""Collection of tests for custom DRF serializers in the account app."""
import random
from unittest.mock import MagicMock, Mock, patch

import faker
from botocore.exceptions import ClientError
from django.test import TestCase
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from account.models import (AwsAccount,
                            AwsInstance,
                            AwsMachineImage,
                            InstanceEvent)
from account.serializers import (AwsAccountSerializer,
                                 aws)
from account.tests import helper as account_helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class AwsAccountSerializerTest(TestCase):
    """AwsAccount serializer test case."""

    @patch('account.serializers.start_image_inspection')
    def test_create_succeeds_when_account_verified(self, mock_copy_snapshot):
        """
        Test saving and processing of a test ARN.

        This is a somewhat comprehensive test that includes finding two
        instances upon initial account discovery. Both instances should get a
        "power on" event. The images for these instances both have random names
        and are owned by other random account IDs. One image has OpenShift.
        """
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        role = util_helper.generate_dummy_role()
        region = random.choice(util_helper.SOME_AWS_REGIONS)

        described_ami1 = util_helper.generate_dummy_describe_image()
        described_ami2 = util_helper.generate_dummy_describe_image(
            openshift=True,
        )

        running_instances = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    image_id=described_ami1['ImageId'],
                    state=aws.InstanceState.running
                ),
                util_helper.generate_dummy_describe_instance(
                    image_id=described_ami2['ImageId'],
                    state=aws.InstanceState.running
                )
            ],
        }

        validated_data = {
            'account_arn': arn,
        }

        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        mock_ami = Mock()
        mock_ami.name = None
        mock_ami.tags = []

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3, \
                patch.object(aws, 'get_running_instances') as mock_get_run, \
                patch.object(aws, 'get_ami') as mock_get_ami, \
                patch.object(aws, 'describe_images') as mock_describe_images:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role
            mock_verify.return_value = True, []
            mock_get_run.return_value = running_instances
            mock_get_ami.return_value = mock_ami
            mock_copy_snapshot.return_value = None

            mock_describe_images.return_value = [
                described_ami1,
                described_ami2,
            ]

            serializer = AwsAccountSerializer(context=context)

            result = serializer.create(validated_data)
            self.assertIsInstance(result, AwsAccount)

        # Verify that we created the account.
        account = AwsAccount.objects.get(aws_account_id=aws_account_id)
        self.assertEqual(aws_account_id, account.aws_account_id)
        self.assertEqual(arn, account.account_arn)

        # Verify that we created both of the instances.
        instances = AwsInstance.objects.filter(account=account).all()
        self.assertEqual(len(instances), 2)
        for region, mock_instances_list in running_instances.items():
            for mock_instance in mock_instances_list:
                instance_id = mock_instance['InstanceId']
                instance = AwsInstance.objects.get(ec2_instance_id=instance_id)
                self.assertIsInstance(instance, AwsInstance)
                self.assertEqual(region, instance.region)
                event = InstanceEvent.objects.get(instance=instance)
                self.assertIsInstance(event, InstanceEvent)
                self.assertEqual(InstanceEvent.TYPE.power_on, event.event_type)

        # Verify that we saved both images used by the running instances.
        amis = AwsMachineImage.objects.all()
        self.assertEqual(len(amis), 2)

        ami = AwsMachineImage.objects.get(ec2_ami_id=described_ami1['ImageId'])
        self.assertFalse(ami.rhel_detected)
        self.assertFalse(ami.openshift_detected)
        self.assertEqual(ami.name, described_ami1['Name'])

        ami = AwsMachineImage.objects.get(ec2_ami_id=described_ami2['ImageId'])
        self.assertFalse(ami.rhel_detected)
        self.assertTrue(ami.openshift_detected)
        self.assertEqual(ami.name, described_ami2['Name'])

        self.assertIsInstance(mock_copy_snapshot.call_args[0][0], str)

    def test_create_fails_when_account_not_verified(self):
        """Test that an account is not saved if verification fails."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        role = util_helper.generate_dummy_role()
        validated_data = {
            'account_arn': arn,
        }

        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        failed_actions = ['foo', 'bar']

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role
            mock_verify.return_value = False, failed_actions
            serializer = AwsAccountSerializer(context=context)

            with self.assertRaises(serializers.ValidationError) as cm:
                serializer.create(validated_data)

            exception = cm.exception
            self.assertIn('account_arn', exception.detail)
            for index in range(len(failed_actions)):
                self.assertIn(failed_actions[index],
                              exception.detail['account_arn'][index + 1])

    def test_create_fails_when_arn_access_denied(self):
        """Test that an account is not saved if ARN access is denied."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        validated_data = {
            'account_arn': arn,
        }

        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        client_error = ClientError(
            error_response={'Error': {'Code': 'AccessDenied'}},
            operation_name=Mock(),
        )

        with patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.side_effect = client_error
            serializer = AwsAccountSerializer(context=context)

            with self.assertRaises(ValidationError) as cm:
                serializer.create(validated_data)
            raised_exception = cm.exception
            self.assertIn('account_arn', raised_exception.detail)
            self.assertIn(arn, raised_exception.detail['account_arn'][0])

    def test_create_fails_when_cloudtrail_fails(self):
        """Test that an account is not saved if cloudtrails errors."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        role = util_helper.generate_dummy_role()

        validated_data = {
            'account_arn': arn,
        }

        client_error = ClientError(
            error_response={'Error': {'Code': 'AccessDeniedException'}},
            operation_name=Mock(),
        )

        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3, \
                patch.object(aws, 'configure_cloudtrail') as mock_cloudtrail:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role
            mock_verify.return_value = True, []
            mock_cloudtrail.side_effect = client_error
            serializer = AwsAccountSerializer(context=context)

            with self.assertRaises(ValidationError) as cm:
                serializer.create(validated_data)
            raised_exception = cm.exception
            self.assertIn('account_arn', raised_exception.detail)
            self.assertIn(arn, raised_exception.detail['account_arn'][0])

    def test_create_fails_when_assume_role_fails_unexpectedly(self):
        """Test that account is not saved if assume_role fails unexpectedly."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        validated_data = {
            'account_arn': arn,
        }

        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        client_error = ClientError(
            error_response=MagicMock(),
            operation_name=Mock(),
        )

        with patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.side_effect = client_error
            serializer = AwsAccountSerializer(context=context)

            with self.assertRaises(ClientError) as cm:
                serializer.create(validated_data)
            raised_exception = cm.exception
            self.assertEqual(raised_exception, client_error)

    def test_create_fails_when_another_arn_has_same_aws_account_id(self):
        """Test that an account is not saved if ARN reuses an AWS account."""
        user = util_helper.generate_test_user()
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        role = util_helper.generate_dummy_role()
        region = random.choice(util_helper.SOME_AWS_REGIONS)
        running_instances = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.running
                ),
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.stopping
                )
            ]
        }

        validated_data = {
            'account_arn': arn,
        }

        # Create one with the same AWS account ID but a different ARN.
        account_helper.generate_aws_account(
            aws_account_id=aws_account_id,
            user=user,
        )

        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3, \
                patch.object(aws, 'get_running_instances') as mock_get_run:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role
            mock_verify.return_value = True, []
            mock_get_run.return_value = running_instances
            serializer = AwsAccountSerializer(context=context)

            with self.assertRaises(ValidationError) as cm:
                serializer.create(validated_data)
            raised_exception = cm.exception
            self.assertIn('account_arn', raised_exception.detail)
            self.assertIn(aws_account_id,
                          raised_exception.detail['account_arn'][0])
