"""Collection of tests for the api.clouds.aws.util module."""
import uuid
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.test import TestCase

from api import AWS_PROVIDER_STRING
from api.clouds.aws import util
from api.clouds.aws.util import generate_aws_ami_messages
from api.tests import helper as api_helper
from util.aws.sqs import _sqs_unwrap_message, _sqs_wrap_message, add_messages_to_queue
from util.tests import helper as util_helper


class CloudsAwsUtilTest(TestCase):
    """Miscellaneous test cases for api.clouds.aws.util module functions."""

    def test_generate_aws_ami_messages(self):
        """Test that messages are formatted correctly."""
        region = util_helper.get_random_region()
        instance = util_helper.generate_dummy_describe_instance()
        instances_data = {region: [instance]}
        ami_list = [instance["ImageId"]]

        expected = [
            {
                "cloud_provider": AWS_PROVIDER_STRING,
                "region": region,
                "image_id": instance["ImageId"],
            }
        ]

        result = generate_aws_ami_messages(instances_data, ami_list)

        self.assertEqual(result, expected)

    def test_sqs_wrap_message(self):
        """Test SQS message wrapping."""
        message_decoded = {"hello": "world"}
        message_encoded = '{"hello": "world"}'
        with patch.object(util.aws.sqs, "uuid") as mock_uuid:
            wrapped_id = uuid.uuid4()
            mock_uuid.uuid4.return_value = wrapped_id
            actual_wrapped = _sqs_wrap_message(message_decoded)
        self.assertEqual(actual_wrapped["Id"], str(wrapped_id))
        self.assertEqual(actual_wrapped["MessageBody"], message_encoded)

    def test_sqs_unwrap_message(self):
        """Test SQS message unwrapping."""
        message_decoded = {"hello": "world"}
        message_encoded = '{"hello": "world"}'
        message_wrapped = {"Body": message_encoded}
        actual_unwrapped = _sqs_unwrap_message(message_wrapped)
        self.assertEqual(actual_unwrapped, message_decoded)

    @patch("api.clouds.aws.util.aws.sqs.boto3")
    def test_add_messages_to_queue(self, mock_boto3):
        """Test that messages get added to a message queue."""
        queue_name = "Test Queue"
        messages, wrapped_messages, __ = api_helper.create_messages_for_sqs()
        mock_sqs = mock_boto3.client.return_value
        mock_queue_url = Mock()
        mock_boto3.client.return_value.get_queue_url.return_value = {
            "QueueUrl": mock_queue_url
        }

        with patch.object(util.aws.sqs, "_sqs_wrap_message") as mock_sqs_wrap_message:
            mock_sqs_wrap_message.return_value = wrapped_messages[0]
            add_messages_to_queue(queue_name, messages)
            mock_sqs_wrap_message.assert_called_once_with(messages[0])

        mock_sqs.send_message_batch.assert_called_with(
            QueueUrl=mock_queue_url, Entries=wrapped_messages
        )


class CloudsAwsUtilCloudTrailTest(TestCase):
    """Test cases for CloudTrail related functions in api.clouds.aws.util."""

    def setUp(self):
        """Set up basic aws account."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(account_id=aws_account_id)
        self.account = api_helper.generate_aws_account(
            aws_account_id=aws_account_id, arn=arn, name="test"
        )

    def test_disable_cloudtrail_success(self):
        """Test disable_cloudtrail normal happy path."""
        with patch.object(util.aws, "get_session"), patch.object(
            util.aws, "disable_cloudtrail"
        ) as mock_disable_cloudtrail:
            success = util.disable_cloudtrail(self.account.content_object)
            mock_disable_cloudtrail.assert_called()
        self.assertTrue(success)

    def test_disable_cloudtrail_not_found(self):
        """
        Test disable_cloudtrail handles when AWS raises an TrailNotFoundException error.

        This could happen if the trail has already been deleted. We treat this as a
        success since the same effective outcome is no trail for us.
        """
        client_error = ClientError(
            error_response={"Error": {"Code": "TrailNotFoundException"}},
            operation_name=Mock(),
        )
        with patch.object(util.aws, "get_session"), patch.object(
            util.aws, "disable_cloudtrail"
        ) as mock_disable_cloudtrail:
            mock_disable_cloudtrail.side_effect = client_error
            success = util.disable_cloudtrail(self.account.content_object)
            mock_disable_cloudtrail.assert_called()
        self.assertTrue(success)

    def test_disable_cloudtrail_access_denied(self):
        """
        Test disable_cloudtrail handles when AWS raises an AccessDenied error.

        This could happen if the user has deleted the AWS account or role. We treat this
        as a non-blocking failure and simply log messages.
        """
        client_error = ClientError(
            error_response={"Error": {"Code": "AccessDenied"}}, operation_name=Mock(),
        )
        expected_warnings = [
            "encountered AccessDenied and cannot disable cloudtrail",
            f"CloudAccount ID {self.account.id}",
        ]
        with self.assertLogs(
            "api.clouds.aws.util", level="WARNING"
        ) as logger, patch.object(util.aws, "get_session"), patch.object(
            util.aws, "disable_cloudtrail"
        ) as mock_disable_cloudtrail:
            mock_disable_cloudtrail.side_effect = client_error
            success = util.disable_cloudtrail(self.account.content_object)
            mock_disable_cloudtrail.assert_called()
            for expected_warning in expected_warnings:
                self.assertIn(expected_warning, logger.output[0])
        self.assertFalse(success)

    def test_disable_cloudtrail_unexpected_error_code(self):
        """
        Test disable_cloudtrail handles when AWS raises an unexpected error code.

        This could happen if AWS is misbehaving unexpectedly. We treat this as a
        non-blocking failure and simply log messages.
        """
        client_error = ClientError(
            error_response={"Error": {"Code": "Potatoes"}}, operation_name=Mock(),
        )
        expected_errors = [
            "Unexpected error Potatoes occurred disabling CloudTrail",
            f"CloudAccount ID {self.account.id}",
        ]
        with self.assertLogs(
            "api.clouds.aws.util", level="ERROR"
        ) as logger, patch.object(util.aws, "get_session"), patch.object(
            util.aws, "disable_cloudtrail"
        ) as mock_disable_cloudtrail:
            mock_disable_cloudtrail.side_effect = client_error
            success = util.disable_cloudtrail(self.account.content_object)
            mock_disable_cloudtrail.assert_called()
            self.assertIn("Traceback", logger.output[0])  # from logger.exception
            for expected_error in expected_errors:
                self.assertIn(expected_error, logger.output[1])  # from logger.error
        self.assertFalse(success)
