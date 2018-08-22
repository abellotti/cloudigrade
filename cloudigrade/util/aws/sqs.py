"""Helper utility module to wrap up common AWS SQS operations."""
import json
import logging

import boto3
from django.conf import settings
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


def _get_queue(queue_url):
    """
    Get the SQS Queue object.

    Args:
        queue_url (str): The AWS assigned URL for the queue.

    Returns:
        Queue: The SQS Queue boto3 resource for the given queue_url.

    """
    region = settings.SQS_DEFAULT_REGION
    queue = boto3.resource('sqs', region_name=region).Queue(queue_url)
    return queue


def receive_messages_from_queue(queue_url, max_number=10, wait_time=10):
    """
    Get message objects from SQS Queue object.

    Args:
        queue_url (str): The AWS assigned URL for the queue.
        max_number (int): Maximum number of messages to receive.
        wait_time (int): Wait time in seconds to receive any messages.

    Returns:
        list[Message]: A list of message objects.

    """
    sqs_queue = _get_queue(queue_url)
    messages = sqs_queue.receive_messages(
        MaxNumberOfMessages=max_number,
        WaitTimeSeconds=wait_time,
    )

    return messages


def yield_messages_from_queue(queue_url, max_number=10, wait_time=10):
    """
    Yield message objects from SQS Queue object.

    Args:
        queue_url (str): The AWS assigned URL for the queue.
        max_number (int): Maximum number of messages to receive.
        wait_time (int): Wait time in seconds to receive any messages.

    Yields:
        Message: An SQS message object.

    """
    sqs_queue = _get_queue(queue_url)
    messages_received = 0
    while messages_received < max_number:
        messages = sqs_queue.receive_messages(
            MaxNumberOfMessages=1,
            WaitTimeSeconds=wait_time,
        )
        if not messages:
            break
        for message in messages:
            messages_received += 1
            yield message


def delete_messages_from_queue(queue_url, messages):
    """
    Delete message objects from SQS queue.

    Args:
        queue_url (str): The AWS assigned URL for the queue.
        messages (list[Message]): A list of message objects to delete.

    Returns:
        dict: The response from the delete call.

    """
    if not messages:
        logger.debug(
            _('{0} received no messages for deletion.   Queue URL {1}').format(
                'delete_messages_from_queue', queue_url))
        return {}

    sqs_queue = _get_queue(queue_url)

    messages_to_delete = [
        {
            'Id': message.message_id,
            'ReceiptHandle': message._receipt_handle
        }
        for message in messages
    ]

    response = sqs_queue.delete_messages(
        Entries=messages_to_delete
    )

    # TODO: Deal with success/failure of message deletes
    return response


def extract_sqs_message(message, service='s3'):
    """
    Parse SQS message for service-specific content.

    Args:
        message (boto3.SQS.Message): The Message object.
        service (str): The AWS service the message refers to.

    Returns:
        list(dict): List of message records.

    """
    extracted_records = []
    message_body = json.loads(message.body)
    for record in message_body.get('Records', []):
        extracted_records.append(record[service])
    return extracted_records
