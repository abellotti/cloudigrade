"""Collection of tests for ``util.insights`` module."""
import base64
import http
import json
from unittest.mock import MagicMock, Mock, patch

import faker
from django.test import TestCase

from util import insights
from util.exceptions import SourcesAPINotJsonContent, SourcesAPINotOkStatus

_faker = faker.Faker()


class InsightsTest(TestCase):
    """Insights module test case."""

    def setUp(self):
        """Set up test data."""
        self.account_number = str(_faker.pyint())
        self.authentication_id = _faker.user_name()
        self.endpoint_id = _faker.pyint()

    def test_generate_http_identity_headers(self):
        """Assert generation of an appropriate HTTP identity headers."""
        known_account_number = "1234567890"
        expected = {
            "X-RH-IDENTITY": (
                "eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMTIzNDU2Nzg5MCJ9fQ=="
            )
        }
        actual = insights.generate_http_identity_headers(known_account_number)
        self.assertEqual(actual, expected)

    def test_generate_org_admin_http_identity_headers(self):
        """Assert generation of an appropriate HTTP identity headers."""
        known_account_number = "1234567890"
        expected = {
            "X-RH-IDENTITY": (
                "eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMTIzND"
                "U2Nzg5MCIsICJ1c2VyIjogeyJpc19vcmdfYWRtaW4iOiB0cnVlfX19"
            )
        }
        actual = insights.generate_http_identity_headers(
            known_account_number, is_org_admin=True
        )
        self.assertEqual(actual, expected)

    @patch("requests.get")
    def test_get_sources_authentication_success(self, mock_get):
        """Assert get_sources_authentication returns response content."""
        expected = {"hello": "world"}
        mock_get.return_value.status_code = http.HTTPStatus.OK
        mock_get.return_value.json.return_value = expected

        authentication = insights.get_sources_authentication(
            self.account_number, self.authentication_id
        )
        self.assertEqual(authentication, expected)
        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_authentication_not_found(self, mock_get):
        """Assert get_sources_authentication returns None if not found."""
        mock_get.return_value.status_code = http.HTTPStatus.NOT_FOUND

        endpoint = insights.get_sources_authentication(
            self.account_number, self.authentication_id
        )
        self.assertIsNone(endpoint)
        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_authentication_fail_not_json(self, mock_get):
        """Assert get_sources_authentication fails when response isn't JSON."""
        mock_get.return_value.status_code = http.HTTPStatus.OK
        mock_get.return_value.json.side_effect = json.decoder.JSONDecodeError(
            Mock(), MagicMock(), MagicMock()
        )
        with self.assertRaises(SourcesAPINotJsonContent):
            insights.get_sources_authentication(
                self.account_number, self.authentication_id
            )
        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_endpoint_success(self, mock_get):
        """Assert get_sources_endpoint returns response content."""
        expected = {"hello": "world"}
        mock_get.return_value.status_code = http.HTTPStatus.OK
        mock_get.return_value.json.return_value = expected

        endpoint = insights.get_sources_endpoint(self.account_number, self.endpoint_id)
        self.assertEqual(endpoint, expected)
        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_authentication_fail_500(self, mock_get):
        """Assert get_sources_authentication fails when response is not-200/404."""
        mock_get.return_value.status_code = http.HTTPStatus.INTERNAL_SERVER_ERROR
        with self.assertRaises(SourcesAPINotOkStatus):
            insights.get_sources_authentication(
                self.account_number, self.authentication_id
            )

        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_endpoint_not_found(self, mock_get):
        """Assert get_sources_endpoint returns None if not found."""
        mock_get.return_value.status_code = http.HTTPStatus.NOT_FOUND

        endpoint = insights.get_sources_endpoint(self.account_number, self.endpoint_id)
        self.assertIsNone(endpoint)
        mock_get.assert_called()

    def test_get_x_rh_identity_header_success(self):
        """Assert get_x_rh_identity_header succeeds for a valid header."""
        expected_value = {"identity": {"account_number": _faker.pyint()}}
        encoded_value = base64.b64encode(json.dumps(expected_value).encode("utf-8"))
        headers = ((_faker.slug(), _faker.slug()), ("x-rh-identity", encoded_value))

        extracted_value = insights.get_x_rh_identity_header(headers)
        self.assertEqual(extracted_value, expected_value)

    def test_get_x_rh_identity_header_missing(self):
        """Assert get_x_rh_identity_header returns empty dict if not found."""
        headers = ((_faker.slug(), _faker.slug()),)

        extracted_value = insights.get_x_rh_identity_header(headers)
        self.assertEqual(extracted_value, {})
