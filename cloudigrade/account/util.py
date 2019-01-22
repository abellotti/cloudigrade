"""Various utility functions for the account app."""
import logging
import math
import uuid
from decimal import Decimal

import boto3
import jsonpickle
from botocore.exceptions import ClientError
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from account import AWS_PROVIDER_STRING
from account.models import (AwsInstance, AwsInstanceEvent, AwsMachineImage,
                            AwsMachineImageCopy, InstanceEvent, MachineImage)
from util import aws

logger = logging.getLogger(__name__)

SQS_SEND_BATCH_SIZE = 10  # boto3 supports sending up to 10 items.
SQS_RECEIVE_BATCH_SIZE = 10  # boto3 supports receiving of up to 10 items.


def create_initial_aws_instance_events(account, instances_data):
    """
    Create AwsInstance and AwsInstanceEvent the first time we see an instance.

    This function is a convenience helper for recording the first time we
    discover a running instance wherein we assume that "now" is the earliest
    known time that the instance was running.

    Args:
        account (AwsAccount): The account that owns the instance that spawned
            the data for these InstanceEvents.
        instances_data (dict): Dict whose keys are AWS region IDs and values
            are each a list of dictionaries that represent an instance
    """
    for region, instances in instances_data.items():
        for instance_data in instances:
            save_instance_events(account, instance_data, region)


def save_instance_events(account, instance_data, region, events=None):
    """
    Save provided events, and create the instance object if it does not exist.

    Note: This function assumes the images related to the instance events have
    already been created and saved.

    Args:
        account (AwsAccount): The account that owns the instance that spawned
            the data for these InstanceEvents.
        instance_data (dict): Dictionary containing instance information.
        region (str): AWS Region.
        events (list[dict]): List of dicts representing Events to be saved.

    Returns:
        AwsInstance: Object representing the saved instance.

    """
    instance, __ = AwsInstance.objects.get_or_create(
        account=account,
        ec2_instance_id=instance_data['InstanceId'] if isinstance(
            instance_data, dict) else instance_data.instance_id,
        region=region,
    )

    if events is None:
        # Assume this is the initial event
        machineimage, created = AwsMachineImage.objects.get_or_create(
            ec2_ami_id=instance_data['ImageId'],
            region=region,
            defaults={'status': MachineImage.UNAVAILABLE})
        if created:
            logger.info(_(
                'Missing image data for {0}; creating UNAVAILABLE stub image.'
            ).format(instance_data))
        event = AwsInstanceEvent(
            instance=instance,
            machineimage=machineimage,
            event_type=InstanceEvent.TYPE.power_on,
            occurred_at=timezone.now(),
            subnet=instance_data['SubnetId'],
            instance_type=instance_data['InstanceType'],
        )
        event.save()
    else:
        logger.info(_('saving {count} new event(s) for {instance}')
                    .format(count=len(events), instance=instance))
        for event in events:
            # When processing events, it's possible that we get information
            # about an instance but we don't know what image was under it
            # because the instance may have been terminated and cleaned up
            # before we could look at it. In that case, we (correctly) have to
            # save the event with no known image.
            machineimage = None
            if event['ec2_ami_id']:
                machineimage = AwsMachineImage.objects.get(
                    ec2_ami_id=event['ec2_ami_id']
                )
            event = AwsInstanceEvent(
                instance=instance,
                machineimage=machineimage,
                event_type=event['event_type'],
                occurred_at=event['occurred_at'],
                subnet=event['subnet'],
                instance_type=event['instance_type'],
            )
            event.save()
    return instance


def create_new_machine_images(session, instances_data):
    """
    Create AwsMachineImage objects that have not been seen before.

    Note:
        During processing, this makes AWS API calls to describe all images
        for the instances found for each region, and we bundle bits of those
        responses with the actual AwsMachineImage creation. We do this all at
        once here to minimize the number of AWS API calls.

    Args:
        session (boto3.Session): The session that found the machine image
        instances_data (dict): Dict whose keys are AWS region IDs and values
            are each a list of dictionaries that represent an instance

    Returns:
        list: A list of image ids that were added to the database

    """
    log_prefix = 'create_new_machine_images'
    seen_ami_ids = {
        instance['ImageId']
        for instances in instances_data.values()
        for instance in instances
    }
    logger.info(_('{prefix}: all AMI IDs found: {seen_ami_ids}')
                .format(prefix=log_prefix, seen_ami_ids=seen_ami_ids))
    known_images = AwsMachineImage.objects.filter(
        ec2_ami_id__in=list(seen_ami_ids)
    )
    known_ami_ids = {
        image.ec2_ami_id for image in known_images
    }
    logger.info(_('{prefix}: Skipping known AMI IDs: {known_ami_ids}')
                .format(prefix=log_prefix, known_ami_ids=known_ami_ids))

    new_described_images = {}
    windows_ami_ids = []

    for region_id, instances in instances_data.items():
        ami_ids = set([instance['ImageId'] for instance in instances])
        new_ami_ids = ami_ids - known_ami_ids
        if new_ami_ids:
            new_described_images[region_id] = (
                aws.describe_images(session, new_ami_ids, region_id)
            )
        windows_ami_ids.extend({
            instance['ImageId']
            for instance in instances
            if aws.is_instance_windows(instance)
        })
    logger.info(_('{prefix}: Windows AMI IDs found: {windows_ami_ids}')
                .format(prefix=log_prefix, windows_ami_ids=windows_ami_ids))

    new_image_ids = []
    for region_id, described_images in new_described_images.items():
        for described_image in described_images:
            ami_id = described_image['ImageId']
            owner_id = Decimal(described_image['OwnerId'])
            name = described_image['Name']
            windows = ami_id in windows_ami_ids
            region = region_id
            openshift = len([
                tag for tag in described_image.get('Tags', [])
                if tag.get('Key') == aws.OPENSHIFT_TAG
            ]) > 0

            logger.info(_('{prefix}: Saving new AMI ID: {ami_id}')
                        .format(prefix=log_prefix, ami_id=ami_id))
            image, new = save_new_aws_machine_image(
                ami_id, name, owner_id, openshift, windows, region)
            if new:
                new_image_ids.append(ami_id)

    return new_image_ids


def save_new_aws_machine_image(ami_id, name, owner_aws_account_id,
                               openshift_detected, windows_detected, region):
    """
    Save a new AwsMachineImage image object.

    Note:
        If an AwsMachineImage already exists with the provided ami_id, we do
        not create a new image nor do we modify the existing one. In that case,
        we simply fetch and return the image with the matching ami_id.

    Args:
        ami_id (str): The AWS AMI ID.
        name (str): the name of the image
        owner_aws_account_id (Decimal): the AWS account ID that owns this image
        openshift_detected (bool): was openshift detected for this image
        windows_detected (bool): was windows detected for this image
        region (str): Region where the image was found

    Returns (AwsMachineImage, bool): The object representing the saved model
        and a boolean of whether it was new or not.

    """
    platform = AwsMachineImage.NONE
    status = AwsMachineImage.PENDING
    if windows_detected:
        platform = AwsMachineImage.WINDOWS
        status = AwsMachineImage.INSPECTED

    ami, new = AwsMachineImage.objects.get_or_create(
        ec2_ami_id=ami_id,
        defaults={
            'platform': platform,
            'owner_aws_account_id': owner_aws_account_id,
            'name': name,
            'status': status,
            'openshift_detected': openshift_detected,
            'region': region,
        }
    )

    return ami, new


def start_image_inspection(arn, ami_id, region):
    """
    Start image inspection of the provided image.

    Args:
        arn (str):  The AWS Resource Number for the account with the snapshot
        ami_id (str): The AWS ID for the machine image
        region (str): The region the snapshot resides in

    Returns:
        AwsMachineImage: Image being inspected

    """
    ami = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
    ami.status = ami.PREPARING
    ami.save()

    if ami.is_marketplace or ami.is_cloud_access:
        ami.status = ami.INSPECTED
        ami.save()
    else:
        # Local import to get around a circular import issue
        from account.tasks import copy_ami_snapshot
        copy_ami_snapshot.delay(arn, ami_id, region)

    return ami


def create_aws_machine_image_copy(copy_ami_id, reference_ami_id):
    """
    Create an AwsMachineImageCopy given the copy and reference AMI IDs.

    Args:
        copy_ami_id (str): the AMI IS of the copied image
        reference_ami_id (str): the AMI ID of the original reference image
    """
    reference = AwsMachineImage.objects.get(ec2_ami_id=reference_ami_id)
    AwsMachineImageCopy.objects.create(
        ec2_ami_id=copy_ami_id,
        owner_aws_account_id=reference.owner_aws_account_id,
        reference_awsmachineimage=reference)


def generate_aws_ami_messages(instances_data, ami_id_list):
    """
    Format information about the machine image for messaging.

    This is a pre-step to sending messages to a message queue.

    Args:
        instances_data (dict): Dict whose keys are AWS region IDs and values
            are each a list of dictionaries that represent an instance
        ami_id_list (list): A list of machine image IDs that need
            messages generated.

    Returns:
        list[dict]: A list of message dictionaries

    """
    messages = []
    for region, instances in instances_data.items():
        for instance in instances:
            if (instance['ImageId'] in ami_id_list and
                    not aws.is_instance_windows(instance)):
                messages.append(
                    {
                        'cloud_provider': AWS_PROVIDER_STRING,
                        'region': region,
                        'image_id': instance['ImageId']
                    }
                )
    return messages


def _sqs_wrap_message(message):
    """
    Wrap the message in a dict for SQS batch sending.

    Args:
        message (object): message to encode and wrap

    Returns:
        dict: structured entry for sending to send_message_batch

    """
    return {
        'Id': str(uuid.uuid4()),
        # Yes, the outgoing message uses MessageBody, not Body.
        'MessageBody': jsonpickle.encode(message),
    }


def _sqs_unwrap_message(sqs_message):
    """
    Unwrap the sqs_message to get the original message.

    Args:
        sqs_message (dict): object to unwrap and decode

    Returns:
        object: the unwrapped and decoded message object

    """
    return jsonpickle.decode(
        # Yes, the response has Body, not MessageBody.
        sqs_message['Body']
    )


def add_messages_to_queue(queue_name, messages):
    """
    Send messages to an SQS queue.

    Args:
        queue_name (str): The queue to add messages to
        messages (list[dict]): A list of message dictionaries. The message
            dicts will be serialized as JSON strings.
    """
    queue_url = aws.get_sqs_queue_url(queue_name)
    sqs = boto3.client('sqs')

    wrapped_messages = [_sqs_wrap_message(message) for message in messages]
    batch_count = math.ceil(len(messages) / SQS_SEND_BATCH_SIZE)

    for batch_num in range(batch_count):
        start_pos = batch_num * SQS_SEND_BATCH_SIZE
        end_pos = start_pos + SQS_SEND_BATCH_SIZE - 1
        batch = wrapped_messages[start_pos:end_pos]
        sqs.send_message_batch(QueueUrl=queue_url, Entries=batch)


def read_messages_from_queue(queue_name, max_count=1):
    """
    Read messages (up to max_count) from an SQS queue.

    Args:
        queue_name (str): The queue to read messages from
        max_count (int): Max number of messages to read

    Returns:
        list[object]: The de-queued messages.

    """
    queue_url = aws.get_sqs_queue_url(queue_name)
    sqs = boto3.client('sqs')
    sqs_messages = []
    max_batch_size = min(SQS_RECEIVE_BATCH_SIZE, max_count)
    for __ in range(max_count):
        # Because receive_message does *not* actually reliably return
        # MaxNumberOfMessages number of messages especially (read the docs),
        # our iteration count is actually max_count and we have some
        # conditions at the end that break us out when we reach the true end.
        new_messages = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=max_batch_size
        ).get('Messages', [])
        if len(new_messages) == 0:
            break
        sqs_messages.extend(new_messages)
        if len(sqs_messages) >= max_count:
            break
    messages = []
    for sqs_message in sqs_messages:
        try:
            unwrapped = _sqs_unwrap_message(sqs_message)
            sqs.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=sqs_message['ReceiptHandle'],
            )
            messages.append(unwrapped)
        except ClientError as e:
            # I'm not sure exactly what exceptions could land here, but we
            # probably should log them, stop attempting further deletes, and
            # return what we have received (and thus deleted!) so far.
            log_message = _(
                'Unexpected error when attempting to read from {0}: {1}'
            ).format(queue_url, getattr(e, 'response', {}).get('Error'))
            logger.error(log_message)
            logger.exception(e)
            break
    return messages


def convert_param_to_int(name, value):
    """Check if a value is convertable to int.

    Args:
        name (str): The field name being validated
        value: The value to convert to int

    Returns:
        int: The int value
    Raises:
        ValidationError if value not convertable to an int

    """
    try:
        return int(value)
    except ValueError:
        error = {
            name: [_('{} must be an integer.'.format(name))]
        }
        raise ValidationError(error)
