"""Helper functions for generating test data."""
import collections
import datetime
import random
import string
import uuid
from decimal import Decimal
from unittest.mock import Mock

import faker
from dateutil import tz
from django.contrib.auth.models import User

from util import aws

SOME_AWS_REGIONS = (
    'ap-northeast-1',
    'ca-central-1',
    'eu-west-1',
    'us-east-1',
    'us-east-2',
)

SOME_EC2_INSTANCE_TYPES = {
    'c5.xlarge': {'memory': 8, 'vcpu': 4},
    'm5.24xlarge': {'memory': 384, 'vcpu': 96},
    'r4.large': {'memory': 15.25, 'vcpu': 2},
    't2.large': {'memory': 16, 'vcpu': 4},
    't2.medium': {'memory': 8, 'vcpu': 2},
    't2.micro': {'memory': 1, 'vcpu': 1},
    't2.nano': {'memory': 0.5, 'vcpu': 1},
    't2.small': {'memory': 2, 'vcpu': 1},
    't2.xlarge': {'memory': 16, 'vcpu': 4},
    'x1e.32xlarge': {'memory': 3904, 'vcpu': 128},
}

MAX_AWS_ACCOUNT_ID = 10**12 - 1


def generate_dummy_aws_account_id():
    """Generate a dummy AWS AwsAccount ID for testing purposes."""
    return Decimal(random.randrange(1, MAX_AWS_ACCOUNT_ID))


def generate_dummy_availability_zone(region=None):
    """Generate a dummy AWS availability zone for testing purposes."""
    if region is None:
        region = random.choice(SOME_AWS_REGIONS)
    return '{}{}'.format(region, random.choice(string.ascii_lowercase))


def generate_dummy_instance_id():
    """Generate a dummy AWS EC2 instance ID for testing purposes."""
    return 'i-{}'.format(
        ''.join(random.choice(string.hexdigits[:16]) for _ in range(17))
    )


def generate_dummy_subnet_id():
    """Generate a dummy AWS EC2 subnet ID for testing purposes."""
    return 'subnet-{}'.format(
        ''.join(random.choice(string.hexdigits[:16]) for _ in range(8))
    )


def generate_dummy_image_id():
    """Generate a dummy AWS image ID for testing purposes."""
    return 'ami-{}'.format(
        ''.join(random.choice(string.hexdigits[:16]) for _ in range(8))
    )


def generate_dummy_snapshot_id():
    """Generate a dummy AWS snapshot ID for testing purposes."""
    return 'snap-{}'.format(
        ''.join(random.choice(string.hexdigits[:16]) for _ in range(17))
    )


def generate_dummy_volume_id():
    """Generate a dummy AWS volume ID for testing purposes."""
    return 'vol-{}'.format(
        ''.join(random.choice(string.hexdigits[:16]) for _ in range(17))
    )


def generate_dummy_arn(account_id=None,
                       region='',
                       partition='aws',
                       service='iam',
                       resource_type='role',
                       resource_separator='/',
                       resource=None):
    """
    Generate a dummy AWS ARN for testing purposes.

    Args:
        account_id (str): Optional account ID. Default is None. If None, an
            account ID will be randomly generated.
        region (str): Optional region. Default is ''.
        partition (str): Optional partition. Default is 'aws'.
        service (str): Optional partition. Default is 'iam'.
        resource_type (str): Optional resource type. Default is 'role'.
        resource_separator (str): A colon ':' or a forward-slash '/'
        resource (str): Optional resource name. Default is None. If None, a
            resource will be randomly generated.

    Returns:
        str: A well-formed, randomized ARN.

    """
    if account_id is None:
        account_id = generate_dummy_aws_account_id()
    if resource is None:
        resource = faker.Faker().name()
    arn = f'arn:{partition}:{service}:{region}:{account_id}:' \
          f'{resource_type}{resource_separator}{resource}'
    return arn


def generate_dummy_describe_instance(instance_id=None, image_id=None,
                                     subnet_id=None, state=None,
                                     instance_type=None, platform=''):
    """
    Generate dummy instance to imitate 'describe instances' API response.

    All arguments are optional, and any not given will be randomly generated.

    Args:
        instance_id (str): Optional EC2 AwsInstance ID.
        image_id (str): Optional AMI ID.
        subnet_id (str): Optional Subnet ID.
        state (aws.InstanceState): Optional known state of the AwsInstance.
        instance_type (str): Optional known EC2 type of AwsInstance.
        platform (str): Optional known Platform value.

    Returns:
        dict: Well-formed instance data structure.

    """
    if state is None:
        state = random.choice(list(aws.InstanceState))

    if image_id is None:
        image_id = generate_dummy_image_id()

    if instance_id is None:
        instance_id = generate_dummy_instance_id()

    if subnet_id is None:
        subnet_id = generate_dummy_subnet_id()

    if instance_type is None:
        instance_type = random.choice(tuple(SOME_EC2_INSTANCE_TYPES.keys()))

    mock_instance = {
        'ImageId': image_id,
        'InstanceId': instance_id,
        'InstanceType': instance_type,
        'Platform': platform,
        'State': {
            'Code': state.value,
            'Name': state.name,
        },
        'SubnetId': subnet_id,
    }
    return mock_instance


def generate_dummy_describe_image(image_id=None, owner_id=None, name=None,
                                  openshift=False):
    """
    Generate dummy image to imitate 'describe images' API response.

    Optional arguments not given may be randomly generated.

    Args:
        image_id (str): Optional AMI ID.
        owner_id (str): Optional AWS Account ID.
        name (str): Optional image name.
        openshift (bool): Optional indicator for openshift.

    Returns:
        dict: Well-formed image data structure.

    """
    if image_id is None:
        image_id = generate_dummy_image_id()

    if owner_id is None:
        owner_id = Decimal(generate_dummy_aws_account_id())

    if name is None:
        name = faker.Faker().bs()

    tags = []
    if openshift:
        tags.append({
            'Key': aws.OPENSHIFT_TAG,
            'Value': aws.OPENSHIFT_TAG,
        })

    mock_image = {
        'ImageId': image_id,
        'OwnerId': owner_id,
        'Name': name,
        'Tags': tags,
    }
    return mock_image


def generate_dummy_role():
    """Generate a dummy AWS role for testing purposes."""
    return {
        'Credentials': {
            'AccessKeyId': str(uuid.uuid4()),
            'SecretAccessKey': str(uuid.uuid4()),
            'SessionToken': str(uuid.uuid4()),
        },
        'foo': 'bar',
    }


def generate_mock_ec2_instance(instance_id=None, image_id=None, subnet_id=None,
                               state=None, instance_type=None, platform=''):
    """
    Generate a mocked EC2 AwsInstance object.

    Args:
        instance_id (str): The EC2 instance id.
        instance_type (str): The EC2 instance type.
        image_id (str): The EC2 AMI image id.
        subnet (str): The EC2 subnet.
        platform (str): The Platform value.

    Returns:
        Mock: A mock object with AwsInstance-like attributes.

    """
    described_instance = generate_dummy_describe_instance(
        instance_id, image_id, subnet_id, state, instance_type, platform
    )
    mock_instance = Mock()
    mock_instance.instance_id = described_instance['InstanceId']
    mock_instance.instance_type = described_instance['InstanceType']
    mock_instance.image_id = described_instance['ImageId']
    mock_instance.state = described_instance['State']
    mock_instance.subnet_id = described_instance['SubnetId']
    mock_instance.platform = described_instance['Platform']
    return mock_instance


def generate_mock_ec2_instance_incomplete(instance_id=None):
    """
    Generate an EC2 Instance-like object for when it is no longer available.

    This can happen in practice when performing a "get instance" API call for
    an instance ID that has been terminated and cleaned up, making the instance
    object data mostly missing.

    Args:
        instance_id (str): optional EC2 instance id

    Returns:
        DummyInstance: An EC2 Instance-like object that will raise an
            AttributeError on all attributes except instance_id.

    """
    if instance_id is None:
        instance_id = generate_dummy_instance_id()

    # HISTORIC NOTE FOR CONTEXT:
    # It would be nice to use the Mock object instead of defining a new class
    # as we are here, and the following example **should** work, as it works
    # for other exception types in the `side_effect` definition, but this
    # pattern **does not work** when using `AttributeError` specifically.
    # instance = MagicMock()
    # type(instance).instance_type = PropertyMock(side_effect=AttributeError)
    # type(instance).image_id = PropertyMock(side_effect=AttributeError)
    # type(instance).state = PropertyMock(side_effect=AttributeError)
    # type(instance).subnet_id = PropertyMock(side_effect=AttributeError)
    # type(instance).platform = PropertyMock(side_effect=AttributeError)

    DummyInstance = collections.namedtuple('DummyInstance', ['instance_id'])
    instance = DummyInstance(instance_id)
    return instance


def generate_mock_image(image_id=None, encrypted=False, state=None):
    """
    Generate a mocked EC2 Image object.

    Args:
        image_id (str): The AMI image id.
        encrypted (bool): Is the image's device encrypted.
        state (str): The state of the image.

    Returns:
        Mock: A mock object with Image-like attributes.

    """
    root_device_name = '/dev/sda1'
    root_device_type = 'ebs'
    volume_types = ('gp2', 'io1', 'st1', 'sc1')
    block_device_mappings = [
        {
            'DeviceName': root_device_name,
            root_device_type.capitalize(): {
                'Encrypted': encrypted,
                'DeleteOnTermination': False,
                'SnapshotId': generate_dummy_snapshot_id(),
                'VolumeSize': random.randint(0, 10),
                'VolumeType': random.choice(volume_types)
            }
        }
    ]

    mock_image = Mock()
    mock_image.image_id = image_id
    mock_image.root_device_name = root_device_name
    mock_image.root_device_type = root_device_type
    mock_image.block_device_mappings = block_device_mappings
    mock_image.state = state
    return mock_image


def generate_mock_image_dict(image_id=None):
    """
    Generate a mocked EC2 image dict.

    Some of the AWS/boto3 APIs return a dict object like this instead of the
    EC2 Image object.

    Args:
        image_id (str): The AMI image id.

    Returns:
        Mock: A dict with attributes similar to what boto3 produces.

    """
    if image_id is None:
        image_id = generate_dummy_image_id()

    mock_image = {
        'ImageId': image_id
    }
    return mock_image


def generate_mock_snapshot(snapshot_id=None, encrypted=False, state=None,
                           owner_id=None):
    """
    Generate a mocked EC2 Image Snapshot object.

    Args:
        snapshot_id (str): The AWS snapshot id.
        encrypted (bool): Indicate if the image is encrypted.
        state (str): The AWS state of the snapshot.
        owner_id (str): The AWS account ID that owns this image.

    Returns:
        Mock: A mock object with Snapshot-like attributes.

    """
    if snapshot_id is None:
        snapshot_id = generate_dummy_snapshot_id()
    if state is None:
        state = 'completed'

    mock_snapshot = Mock()
    mock_snapshot.snapshot_id = snapshot_id
    mock_snapshot.encrypted = encrypted
    mock_snapshot.state = state
    mock_snapshot.owner_id = owner_id
    return mock_snapshot


def generate_mock_volume(volume_id=None,
                         snapshot_id=None,
                         zone=None,
                         state=None):
    """
    Generate a mocked EC2 EBS Volume object.

    Args:
        volume_id (str): Optional volume id.
        snapshot_id (str): Optional snapshot id.
        zone (str): Optional availability zone.

    Returns:
        Mock: A mock object with Volume-like attributes.

    """
    if volume_id is None:
        volume_id = generate_dummy_volume_id()
    if snapshot_id is None:
        snapshot_id = generate_dummy_snapshot_id()
    if zone is None:
        zone = generate_dummy_availability_zone()
    if state is None:
        state = random.choice(
            ('creating', 'available', 'in-use', 'deleting', 'deleted', 'error')
        )

    mock_volume = Mock()
    mock_volume.id = volume_id
    mock_volume.snapshot_id = snapshot_id
    mock_volume.zone = zone
    mock_volume.state = state
    return mock_volume


def generate_mock_sqs_message(message_id, body, receipt_handle):
    """
    Generate a mocked SQS Message object.

    Args:
        message_id (str): The SQS message id.
        body (str): The message contents.
        receipt_handle (str): The SQS receipt handle.

    Returns:
        Mock: A mock object with Message-like attributes.

    """
    mock_message = Mock()
    mock_message.Id = message_id
    mock_message.ReceiptHandle = receipt_handle
    mock_message.body = body
    return mock_message


def utc_dt(*args, **kwargs):
    """Wrap datetime construction to force result to UTC.

    Returns:
        datetime.datetime

    """
    return datetime.datetime(*args, **kwargs).replace(
        tzinfo=tz.tzutc()
    )


def generate_test_user(email=None, is_superuser=False):
    """
    Generate and save a user for testing.

    Args:
        email (str): optional email address
        is_superuser (bool): create as a superuser if True

    Returns:
        User: created Django auth User

    """
    if not email:
        # We're specifically not using faker here because we want to be very
        # confident that the address domain is not real.
        name = ''.join(random.choice(string.ascii_letters) for __ in range(32))
        email = f'{name}@mail.127.0.0.1.nip.io'
    user = User.objects.create_user(
        username=email,
        email=email,
        password=''.join(random.choice(string.printable) for __ in range(128)),
        is_superuser=is_superuser,
    )
    return user
