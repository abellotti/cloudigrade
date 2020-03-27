"""Functions and classes for interacting with Insights platform services."""
import base64
import http
import json
import logging

import requests
from django.conf import settings
from django.utils.translation import gettext as _

from util.exceptions import SourcesAPINotJsonContent, SourcesAPINotOkStatus

logger = logging.getLogger(__name__)


def generate_http_identity_headers(account_number, is_org_admin=False):
    """
    Generate an Insights-specific identity HTTP header.

    For calls to the Authentication API, the account_number must match the
    customer's account number, and is_org_admin should be set to True.

    Args:
        account_number (str): account number identifier for Insights auth
        is_org_admin (bool): boolean for creating an org admin header

    Returns:
        dict with encoded Insights identity header

    """
    raw_header = {"identity": {"account_number": account_number}}
    if is_org_admin:
        raw_header["identity"]["user"] = {"is_org_admin": True}
    identity_encoded = base64.b64encode(json.dumps(raw_header).encode("utf-8")).decode(
        "utf-8"
    )
    headers = {"X-RH-IDENTITY": identity_encoded}
    return headers


def get_sources_authentication(account_number, authentication_id):
    """
    Get an Authentication objects from the Sources API.

    If the `requests.get` itself fails unexpectedly, let the exception bubble
    up to be handled by a higher level in the stack.

    Args:
        account_number (str): account number identifier for Insights auth
        authentication_id (int): the requested authentication's id

    Returns:
        dict response payload from the sources api.

    """
    sources_api_base_url = settings.SOURCES_API_BASE_URL
    sources_api_internal_uri = settings.SOURCE_API_INTERNAL_URI

    url = (
        f"{sources_api_base_url}/{sources_api_internal_uri}"
        f"authentications/{authentication_id}/"
    )

    headers = generate_http_identity_headers(account_number, is_org_admin=True)
    params = {"expose_encrypted_attribute[]": "password"}

    return make_sources_call(account_number, url, headers, params)


def get_sources_endpoint(account_number, endpoint_id):
    """
    Get an Endpoint object from the Sources API.

    If the `requests.get` itself fails unexpectedly, let the exception bubble
    up to be handled by a higher level in the stack.

    Args:
        account_number (str): account number identifier for Insights auth
        endpoint_id (int): the requested endpoint's id

    Returns:
        dict response payload from the sources api.
    """
    sources_api_base_url = settings.SOURCES_API_BASE_URL
    sources_api_external_uri = settings.SOURCES_API_EXTERNAL_URI

    url = f"{sources_api_base_url}/{sources_api_external_uri}endpoints/{endpoint_id}/"

    headers = generate_http_identity_headers(account_number, is_org_admin=True)
    return make_sources_call(account_number, url, headers)


def get_sources_application(account_number, application_id):
    """
    Get an Application object from the Sources API.

    If the `requests.get` itself fails unexpectedly, let the exception bubble
    up to be handled by a higher level in the stack.

    Args:
        account_number (str): account number identifier for Insights auth
        application_id (int): the requested application's id

    Returns:
        dict response payload from the sources api.
    """
    sources_api_base_url = settings.SOURCES_API_BASE_URL
    sources_api_external_uri = settings.SOURCES_API_EXTERNAL_URI

    url = (
        f"{sources_api_base_url}/{sources_api_external_uri}"
        f"applications/{application_id}/"
    )

    headers = generate_http_identity_headers(account_number, is_org_admin=True)
    return make_sources_call(account_number, url, headers)


def make_sources_call(account_number, url, headers, params=None):
    """
    Make an API call to the Sources API.

    If the `requests.get` itself fails unexpectedly, let the exception bubble
    up to be handled by a higher level in the stack.

    Args:
        account_number (str): account number identifier for Insights auth
        url (str): the requested url
        headers (dict): a dict of headers for the request.
        params (dict): a dict of params for the request

    Returns:
        dict response payload from the sources api or None if not found.
    """
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == http.HTTPStatus.NOT_FOUND:
        return None
    elif response.status_code != http.HTTPStatus.OK:
        message = _(
            "unexpected status {status} using account {account_number} at {url}"
        ).format(status=response.status_code, account_number=account_number, url=url)
        raise SourcesAPINotOkStatus(message)

    try:
        response_json = response.json()
    except json.decoder.JSONDecodeError:
        message = _(
            "unexpected non-json response using account {account_number} at {url}"
        ).format(account_number=account_number, url=url)
        raise SourcesAPINotJsonContent(message)

    return response_json


def get_x_rh_identity_header(headers):
    """
    Get the x-rh-identity contents from the Kafka topic message headers.

    Args:
        headers (list[tuple]): the headers of a message from a Kafka topic
            generated by the Sources service

    Returns:
        dict contents of the x-rh-identity header.
    """
    auth_header = {}
    # The headers are a list of... tuples.
    for header in headers:
        if header[0] == "x-rh-identity":
            auth_header = json.loads(base64.b64decode(header[1]).decode("utf-8"))
            break

    return auth_header


def extract_ids_from_kafka_message(message, headers):
    """
    Get the account_number and platform_id from the Kafka topic message and headers.

    Args:
        message (dict): the "value" attribute of a message from a Kafka
            topic generated by the Sources service
        headers (list[tuple]): the headers of a message from a Kafka topic
            generated by the Sources service

    Returns:
        (account_number, platform_id) (str, str):
            the extracted account number and platform id.
    """
    auth_header = get_x_rh_identity_header(headers)
    if not auth_header:
        logger.error(
            _("Missing expected auth header from message %s, headers %s"),
            message,
            headers,
        )

    account_number = auth_header.get("identity", {}).get("account_number")
    if not account_number:
        logger.error(
            _("Missing expected account number from message %s, headers %s"),
            message,
            headers,
        )

    platform_id = message.get("id")
    if not platform_id:
        logger.error(
            _("Missing expected id from message %s, headers %s"), message, headers
        )

    return account_number, platform_id


def get_sources_cloudigrade_application_type_id(account_number):
    """Get the cloudigrade application type id from sources."""
    sources_api_base_url = settings.SOURCES_API_BASE_URL
    sources_api_external_uri = settings.SOURCES_API_EXTERNAL_URI
    url = (
        f"{sources_api_base_url}/{sources_api_external_uri}"
        f"application_types?filter[name]=/insights/platform/cloud-meter"
    )

    headers = generate_http_identity_headers(account_number)
    cloudigrade_application_type = make_sources_call(account_number, url, headers)
    if cloudigrade_application_type:
        return cloudigrade_application_type.get("data")[0].get("id")
    return None


def notify_sources_application_availability(
    account_number, application_id, availability_status, availability_status_error=""
):
    """
    Update Sources application's availability status.

    Args:
        account_number (str): account number identifier for Insights auth
        application_id (int): Platform insights application id
        availability_status (string): Availability status to set
        availability_status_error (string): Optional status error
    """
    sources_api_base_url = settings.SOURCES_API_BASE_URL
    sources_api_external_uri = settings.SOURCES_API_EXTERNAL_URI

    url = (
        f"{sources_api_base_url}/{sources_api_external_uri}"
        f"applications/{application_id}/"
    )
    payload = {
        "availability_status": availability_status,
        "availability_status_error": availability_status_error,
    }

    logger.info(
        _(
            "Setting the availability status for application "
            "%(application_id)s as %(status)s"
        ),
        {"application_id": application_id, "status": availability_status},
    )

    headers = generate_http_identity_headers(account_number, is_org_admin=True)
    response = requests.patch(url, headers=headers, data=json.dumps(payload))

    if response.status_code == http.HTTPStatus.NOT_FOUND:
        logger.info(
            _(
                "Cannot update availability status, application id "
                "%(application_id)s not found."
            ),
            {"application_id": application_id},
        )
    elif response.status_code != http.HTTPStatus.NO_CONTENT:
        message = _(
            "Unexpected status {status} updating application "
            "{application_id} status at {url}"
        ).format(status=response.status_code, application_id=application_id, url=url)
        raise SourcesAPINotOkStatus(message)
