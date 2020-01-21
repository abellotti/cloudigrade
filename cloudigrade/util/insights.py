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


def generate_http_identity_headers(account_number):
    """
    Generate an Insights-specific identity HTTP header.

    Args:
        account_number (str): account number identifier for Insights auth

    Returns:
        dict with encoded Insights identity header

    """
    raw_header = {"identity": {"account_number": account_number}}
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
    url = f"{sources_api_base_url}/authentications/{authentication_id}/"

    headers = generate_http_identity_headers(account_number)
    params = {"expose_encrypted_attribute[]": "password"}

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != http.HTTPStatus.OK:
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
