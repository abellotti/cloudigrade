"""Collection of tests for custom Django model logic."""
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.db.utils import IntegrityError
from django.test import TestCase

from account import models
from account.tests import helper as account_helper
from util.aws import sts
from util.exceptions import CloudTrailCannotStopLogging
from util.tests import helper as util_helper


class AwsAccountModelTest(TestCase):
    """AwsAccount Model Test Cases."""

    def setUp(self):
        """Set up basic aws account."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(account_id=aws_account_id)
        self.role = util_helper.generate_dummy_role()
        self.account = account_helper.generate_aws_account(
            aws_account_id=aws_account_id,
            arn=arn,
            name='test'
        )

    def test_save_fails_when_name_is_blank(self):
        """Test that we cannot save an account with an empty name."""
        with self.assertRaises(IntegrityError):
            models.AwsAccount.objects.create(
                name=None
            )

    def test_delete_succeeds(self):
        """Test that an account is deleted if there are no errors."""
        with patch.object(sts, 'boto3') as mock_boto3,\
                patch.object(models, 'disable_cloudtrail'):
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            self.account.delete()
            self.assertEqual(0, models.AwsAccount.objects.count())

    def test_delete_succeeds_on_access_denied_exception(self):
        """Test that the account is deleted on AccessDeniedException."""
        client_error = ClientError(
            error_response={'Error': {'Code': 'AccessDeniedException'}},
            operation_name=Mock(),
        )

        with patch.object(models, 'disable_cloudtrail') as mock_cloudtrail,\
                patch.object(sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_cloudtrail.side_effect = client_error

            self.account.delete()

        self.assertEqual(0, models.AwsAccount.objects.count())

    def test_delete_fails_on_other_cloudtrail_exception(self):
        """Test that the account is not deleted on other cloudtrail error."""
        client_error = ClientError(
            error_response={'Error': {'Code': 'OtherException'}},
            operation_name=Mock(),
        )

        with patch.object(models, 'disable_cloudtrail') as mock_cloudtrail,\
                patch.object(sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_cloudtrail.side_effect = client_error

            with self.assertRaises(CloudTrailCannotStopLogging):
                self.account.delete()

        self.assertEqual(1, models.AwsAccount.objects.count())

    def test_delete_succeeds_when_cloudtrial_does_not_exist(self):
        """Test that an account is deleted if cloudtrail does not exist."""
        client_error = ClientError(
            error_response={'Error': {'Code': 'TrailNotFoundException'}},
            operation_name=Mock(),
        )

        with patch.object(models, 'disable_cloudtrail') as mock_cloudtrail,\
                patch.object(sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_cloudtrail.side_effect = client_error

            self.account.delete()

        self.assertEqual(0, models.AwsAccount.objects.count())

    def test_delete_succeeds_when_aws_account_cannot_be_accessed(self):
        """Test that an account is deleted if cloudtrail does not exist."""
        client_error = ClientError(
            error_response={'Error': {'Code': 'AccessDenied'}},
            operation_name=Mock(),
        )

        with patch.object(models, 'disable_cloudtrail') as mock_cloudtrail,\
                patch.object(sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_cloudtrail.side_effect = client_error

            self.account.delete()

        self.assertEqual(0, models.AwsAccount.objects.count())

    def test_marketplace_is_not_rhel(self):
        """Test that marketplace images are not tracked as RHEL."""
        image = account_helper.generate_aws_image(
            is_marketplace=True,
        )
        self.assertFalse(image.rhel)
        self.assertFalse(image.rhel_detected)
        self.assertTrue(image.is_marketplace)

    def test_rhel_not_detected_but_is_cloud_access_is_rhel(self):
        """Test that cloud access images are always tracked as RHEL."""
        image = account_helper.generate_aws_image(
            rhel_detected=False,
            is_cloud_access=True,
        )
        self.assertTrue(image.rhel)
        self.assertTrue(image.rhel_detected)
        self.assertTrue(image.is_cloud_access)
        self.assertFalse(image.rhel_enabled_repos_found)
        self.assertFalse(image.rhel_product_certs_found)
        self.assertFalse(image.rhel_release_files_found)
        self.assertFalse(image.rhel_signed_packages_found)

    def test_is_marketplace_check_is_case_insensitive(self):
        """Assert is_marketplace check is case-insensitive."""
        image = account_helper.generate_aws_image(is_marketplace=True)
        image.name = image.name.upper()
        image.save()
        image.refresh_from_db()
        self.assertTrue(image.is_marketplace)

        image.name = image.name.lower()
        image.save()
        image.refresh_from_db()
        self.assertTrue(image.is_marketplace)

    def test_is_cloud_access_check_is_case_insensitive(self):
        """Assert is_cloud_access check is case-insensitive."""
        image = account_helper.generate_aws_image(is_cloud_access=True)
        image.name = image.name.upper()
        image.save()
        image.refresh_from_db()
        self.assertTrue(image.is_cloud_access)

        image.name = image.name.lower()
        image.save()
        image.refresh_from_db()
        self.assertTrue(image.is_cloud_access)
