"""Collection of tests for the cloudtrail module."""
from django.test import TestCase

from analyzer import cloudtrail
from analyzer.tests import helper as analyzer_helper
from util.tests import helper as util_helper


class ExtractEC2InstanceEventsTest(TestCase):
    """Extract EC2 instance events test case."""

    def test_extract_ec2_instance_events_invalid_event(self):
        """Assert that no events are extracted from an invalid record."""
        record = {'potato': 'gems'}
        expected = []
        extracted = cloudtrail.extract_ec2_instance_events(record)
        self.assertEqual(extracted, expected)

    def test_extract_ec2_instance_events_missing_instancetype(self):
        """Assert that no events are extracted if instance type is missing."""
        record = analyzer_helper.generate_cloudtrail_record(
            util_helper.generate_dummy_aws_account_id(),
            'ModifyInstanceAttribute'
        )
        expected = []
        extracted = cloudtrail.extract_ec2_instance_events(record)
        self.assertEqual(extracted, expected)
