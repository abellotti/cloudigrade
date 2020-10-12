"""Celery tasks related to the AWS image inspection process."""
import logging

import boto3
from botocore.exceptions import ClientError
from celery import shared_task
from django.conf import settings
from django.utils.translation import gettext as _

from api.clouds.aws.models import AwsMachineImage
from api.clouds.aws.util import (
    update_aws_image_status_error,
    update_aws_image_status_inspected,
)
from api.models import MachineImage
from util import aws
from util.celery import retriable_shared_task
from util.exceptions import (
    AwsECSInstanceNotReady,
    AwsTooManyECSInstances,
)
from util.misc import generate_device_name, get_now

logger = logging.getLogger(__name__)


@retriable_shared_task(name="api.clouds.aws.tasks.scale_down_cluster")
@aws.rewrap_aws_errors
def scale_down_cluster():
    """
    Scale down cluster after houndigrade scan.

    Returns:
        None: Run as an asynchronous Celery task.

    """
    logger.info(_("Scaling down ECS cluster."))
    aws.scale_down(settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME)


@shared_task(name="api.clouds.aws.tasks.scale_up_inspection_cluster")
@aws.rewrap_aws_errors
def scale_up_inspection_cluster():
    """
    Scale up the "houndigrade" inspection cluster.

    Returns:
        None: Run as a scheduled Celery task.

    """
    queue_name = "{0}ready_volumes".format(settings.AWS_NAME_PREFIX)
    scaled_down, auto_scaling_group = aws.is_scaled_down(
        settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
    )
    if not scaled_down:
        # Quietly exit and let a future run check the scaling.
        args = {
            "name": settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME,
            "min_size": auto_scaling_group.get("MinSize"),
            "max_size": auto_scaling_group.get("MinSize"),
            "desired_capacity": auto_scaling_group.get("DesiredCapacity"),
            "len_instances": len(auto_scaling_group.get("Instances", [])),
        }
        logger.info(
            _(
                'Auto Scaling group "%(name)s" is not scaled down. '
                "MinSize=%(min_size)s MaxSize=%(max_size)s "
                "DesiredCapacity=%(desired_capacity)s "
                "len(Instances)=%(len_instances)s"
            ),
            args,
        )
        instance_ids = [
            instance.get("InstanceId")
            for instance in auto_scaling_group.get("Instances", [])
        ]
        check_cluster_instances_age(instance_ids)
        return

    messages = aws.read_messages_from_queue(
        queue_name, settings.HOUNDIGRADE_AWS_VOLUME_BATCH_SIZE
    )

    if len(messages) == 0:
        # Quietly exit and let a future run check for messages.
        logger.info(_("Not scaling up because no new volumes were found."))
        return

    try:
        aws.scale_up(settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME)
    except ClientError:
        # If scale_up fails unexpectedly, requeue messages so they aren't lost.
        aws.add_messages_to_queue(queue_name, messages)
        raise

    attach_volumes_to_cluster.delay(messages)


def describe_cluster_instances(instance_ids):
    """
    Describe multiple AWS EC2 Instances.

    This is simply a convenience wrapper for util.aws.describe_instances since the
    inspection process always uses our default session and cluster region.

    Args:
        instance_ids (list[str]): The EC2 instance IDs

    Returns:
        list(dict): List of dicts that describe the requested instances

    """
    session = boto3.Session()
    region = aws.ECS_CLUSTER_REGION
    return aws.describe_instances(session, instance_ids, region)


def check_cluster_instances_age(instance_ids):
    """
    Check the age of the given ECS cluster EC2 instance IDs.

    This function returns nothing, but it will log an error for any instance
    that exists with a launch time ago older than the configured limit.

    Args:
        instance_ids (list): list of EC2 instance IDs
    """
    if not instance_ids:
        return

    for instance_id in instance_ids:
        logger.info(_("Inspection cluster instance exists: %s"), instance_id)

    instances = describe_cluster_instances(instance_ids)

    age_limit = settings.INSPECTION_CLUSTER_INSTANCE_AGE_LIMIT
    now = get_now()

    for (ec2_instance_id, described_instance) in instances.items():
        state = described_instance.get("State", {}).get("Name")
        launch_time = described_instance.get("LaunchTime")
        if not launch_time:
            logger.error(
                _(
                    "Inspection cluster instance %(ec2_instance_id)s has state "
                    "%(state)s but no launch time."
                ),
                {"ec2_instance_id": ec2_instance_id, "state": state},
            )
            continue

        launch_age = round((now - launch_time).total_seconds(), 1)
        if launch_age > age_limit:
            logger.error(
                _(
                    "Inspection cluster instance %(ec2_instance_id)s has state "
                    "%(state)s and launched %(launch_age)s seconds ago at "
                    "%(launch_time)s. This exceeds our configured limit of "
                    "%(age_limit)s seconds by %(delta)s seconds."
                ),
                {
                    "ec2_instance_id": ec2_instance_id,
                    "state": state,
                    "launch_time": launch_time,
                    "launch_age": launch_age,
                    "age_limit": age_limit,
                    "delta": round(launch_age - age_limit, 1),
                },
            )
        else:
            logger.debug(
                _(
                    "Inspection cluster instance %(ec2_instance_id)s has state "
                    "%(state)s and launched %(launch_age)s seconds ago at "
                    "%(launch_time)s. This fits within our configured limit of "
                    "%(age_limit)s seconds by %(delta)s seconds."
                ),
                {
                    "ec2_instance_id": ec2_instance_id,
                    "state": state,
                    "launch_time": launch_time,
                    "launch_age": launch_age,
                    "age_limit": age_limit,
                    "delta": round(age_limit - launch_age, 1),
                },
            )


@retriable_shared_task(name="api.clouds.aws.tasks.attach_volumes_to_cluster")
@aws.rewrap_aws_errors
def attach_volumes_to_cluster(messages):  # noqa: C901
    """
    Ensure houndigrade cluster instance is ready and attach volumes for inspection.

    Args:
        messages (list): list of dicts describing images to inspect. items look like
            {"ami_id": "ami-1234567890", "volume_id": "vol-1234567890"}

    Returns:
        None: Run as an asynchronous Celery task.

    """
    relevant_messages = _filter_messages_for_inspection(messages)

    if not relevant_messages:
        # Early return if nothing actually needs inspection.
        # The cluster has likely scaled up now and needs to scale down.
        scale_down_cluster.delay()
        return

    ecs = boto3.client("ecs")
    # get ecs container instance id
    result = ecs.list_container_instances(
        cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME, status="ACTIVE"
    )

    # verify we have our single container instance
    num_instances = len(result["containerInstanceArns"])
    if num_instances == 0:
        raise AwsECSInstanceNotReady
    elif num_instances > 1:
        raise AwsTooManyECSInstances

    result = ecs.describe_container_instances(
        containerInstances=[result["containerInstanceArns"][0]],
        cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME,
    )
    ec2_instance_id = result["containerInstances"][0]["ec2InstanceId"]

    # Obtain boto EC2 Instance
    ec2 = boto3.resource("ec2")
    ec2_instance = ec2.Instance(ec2_instance_id)
    current_state = ec2_instance.state
    if not aws.InstanceState.is_running(current_state["Code"]):
        logger.warning(
            _(
                "ECS cluster %(cluster)s has container instance %(ec2_instance_id)s "
                "but instance state is %(current_state)s"
            ),
            {
                "cluster": settings.HOUNDIGRADE_ECS_CLUSTER_NAME,
                "ec2_instance_id": ec2_instance_id,
                "current_state": current_state,
            },
        )
        raise AwsECSInstanceNotReady

    logger.info(_("%s attaching volumes"), "attach_volumes_to_cluster")

    # attach volumes and track which AMI is used at which mount point
    ami_mountpoints = []
    for index, message in enumerate(relevant_messages):
        ec2_ami_id = message["ami_id"]
        ec2_volume_id = message["volume_id"]
        mount_point = generate_device_name(index)
        volume = ec2.Volume(ec2_volume_id)
        logger.info(
            _(
                "%(label)s attaching volume %(volume_id)s from AMI "
                "%(ami_id)s to instance %(instance)s at %(mount_point)s"
            ),
            {
                "label": "run_inspection_cluster",
                "volume_id": ec2_volume_id,
                "ami_id": ec2_ami_id,
                "instance": ec2_instance_id,
                "mount_point": mount_point,
            },
        )
        try:
            volume.attach_to_instance(Device=mount_point, InstanceId=ec2_instance_id)
        except ClientError as e:
            error_code = e.response.get("Error").get("Code")
            error_message = e.response.get("Error").get("Message")

            if (
                error_code in ("OptInRequired", "IncorrectInstanceState")
                and "marketplace" in error_message.lower()
            ):
                logger.info(
                    _(
                        'Found a marketplace AMI "%s" when trying to copy '
                        "volume. This should not happen, but here we are."
                    ),
                    ec2_ami_id,
                )
                save_success = update_aws_image_status_inspected(ec2_ami_id)
            else:
                logger.error(
                    _(
                        "Encountered an issue when trying to attach "
                        'volume "%(volume_id)s" from AMI "%(ami_id)s" '
                        "to inspection instance. Error code: "
                        '"%(error_code)s". Error message: '
                        '"%(error_message)s". Setting image state to '
                        "ERROR."
                    ),
                    {
                        "volume_id": ec2_volume_id,
                        "ami_id": ec2_ami_id,
                        "error_code": error_code,
                        "error_message": error_message,
                    },
                )
                save_success = update_aws_image_status_error(ec2_ami_id)

            if not save_success:
                logger.warning(
                    _(
                        "Failed to save updated status to AwsMachineImage for "
                        "EC2 AMI ID %(ec2_ami_id)s in run_inspection_cluster"
                    ),
                    {"ec2_ami_id": ec2_ami_id},
                )

            volume.delete()
            continue

        logger.info(
            _("%(label)s modify volume %(volume_id)s to auto-delete"),
            {"label": "run_inspection_cluster", "volume_id": ec2_volume_id},
        )
        # Configure volumes to delete when instance is scaled down
        ec2_instance.modify_attribute(
            BlockDeviceMappings=[
                {
                    "DeviceName": mount_point,
                    "Ebs": {"DeleteOnTermination": True},
                }
            ]
        )

        ami_mountpoints.append((message["ami_id"], mount_point))

    if not ami_mountpoints:
        logger.warning(_("No targets left to inspect, exiting early."))
        return

    run_inspection_cluster.delay(ec2_instance_id, ami_mountpoints)


def _filter_messages_for_inspection(messages):
    """
    Filter messages to only images that exist for inspection.

    Important note: This also has the side effect of *updating* our saved models to
    indicate that the relevant images now have the "inspecting" status.

    Args:
        messages (list): list of dicts describing images to inspect. items look like
            {"ami_id": "ami-1234567890", "volume_id": "vol-1234567890"}

    Returns:
        list of dicts describing images to inspect. items look like
        {"ami_id": "ami-1234567890", "volume_id": "vol-1234567890"}

    """
    relevant_messages = []
    for message in messages:
        try:
            ec2_ami_id = message.get("ami_id")
            aws_machine_image = AwsMachineImage.objects.get(ec2_ami_id=ec2_ami_id)
            machine_image = aws_machine_image.machine_image.get()
            machine_image.status = MachineImage.INSPECTING
            machine_image.save()
            relevant_messages.append(message)
        except AwsMachineImage.DoesNotExist:
            logger.warning(
                _(
                    "Skipping inspection because we do not have an "
                    "AwsMachineImage for %(ec2_ami_id)s (%(message)s)"
                ),
                {"ec2_ami_id": ec2_ami_id, "message": message},
            )
        except MachineImage.DoesNotExist:
            logger.warning(
                _(
                    "Skipping inspection because we do not have a "
                    "MachineImage for %(ec2_ami_id)s (%(message)s)"
                ),
                {"ec2_ami_id": ec2_ami_id, "message": message},
            )
    return relevant_messages


def _build_task_command(cloud, ami_mountpoints):
    """
    Build the command arguments for the houndigrade task.

    Todo:
        When we add support for additional cloud providers like Azure, this function
        should be moved and generally repurposed if we continue using houndigrade the
        same way for those other clouds.

    Args:
        cloud (str): identifier token for the cloud provider type (e.g. "aws")
        ami_mountpoints (list): list of tuples each having (ami_id, mount_point)

    Returns:
        list of strings that make up the command arguments for the houndigrade task

    """
    task_command = ["-c", cloud]
    for ami_id, mount_point in ami_mountpoints:
        task_command.extend(["-t", ami_id, mount_point])
    return task_command


def _check_cluster_volume_mounts(ec2_instance_id, ami_mountpoints):
    """
    Check that the cluster instance has devices attached at the expected mount points.

    Args:
        ec2_instance_id (str): EC2 instance ID of the running houndigrade instance
        ami_mountpoints (list): list of tuples each having (ami_id, mount_point)

    Returns:
        bool true if the cluster has devices attached at the expected mount points

    """
    instance = describe_cluster_instances([ec2_instance_id])[ec2_instance_id]
    device_mappings = dict(
        (mapping["DeviceName"], mapping) for mapping in instance["BlockDeviceMappings"]
    )
    incomplete_mounts = False
    for ami_id, mount_point in ami_mountpoints:
        device_mapping = device_mappings.get(mount_point, {})
        status = device_mapping.get("Ebs", {}).get("Status")
        if not device_mapping:
            logger.error(
                _(
                    "Expected device %(mount_point)s for %(ami_id)s not found in "
                    "described instance %(ec2_instance_id)s"
                ),
                {
                    "mount_point": mount_point,
                    "ami_id": ami_id,
                    "ec2_instance_id": ec2_instance_id,
                },
            )
            incomplete_mounts = True
        elif status == "attaching":
            logger.info(
                _(
                    "Device %(mount_point)s for %(ami_id)s is still attaching to "
                    "instance %(ec2_instance_id)s"
                ),
                {
                    "mount_point": mount_point,
                    "ami_id": ami_id,
                    "ec2_instance_id": ec2_instance_id,
                },
            )
            incomplete_mounts = True
        elif status != "attached":
            logger.error(
                _(
                    "Expected device %(mount_point)s for %(ami_id)s has unexpected "
                    "status %(status)s for instance %(ec2_instance_id)s; "
                    "current described block device mapping is %(detail)s"
                ),
                {
                    "mount_point": mount_point,
                    "ami_id": ami_id,
                    "ec2_instance_id": ec2_instance_id,
                    "status": status,
                    "detail": device_mapping,
                },
            )
            incomplete_mounts = True

    return not incomplete_mounts


@retriable_shared_task(name="api.clouds.aws.tasks.run_inspection_cluster")
@aws.rewrap_aws_errors
def run_inspection_cluster(ec2_instance_id, ami_mountpoints):
    """
    Run task definition for houndigrade on the cluster.

    Args:
        ec2_instance_id (str): EC2 instance ID of the running houndigrade instance
        ami_mountpoints (list): list of tuples each having (ami_id, mount_point)

    Returns:
        None: Run as an asynchronous Celery task.

    """
    volumes_mounted = _check_cluster_volume_mounts(ec2_instance_id, ami_mountpoints)
    if not volumes_mounted:
        raise AwsECSInstanceNotReady

    task_command = _build_task_command("aws", ami_mountpoints)
    container_definition = _build_container_definition(task_command)

    ecs = boto3.client("ecs")
    result = ecs.register_task_definition(
        family=f"{settings.HOUNDIGRADE_ECS_FAMILY_NAME}",
        containerDefinitions=[container_definition],
        requiresCompatibilities=["EC2"],
    )
    task_definition_arn = result["taskDefinition"]["taskDefinitionArn"]

    # release the hounds
    logger.info(
        _("Running task %(task_definition)s in cluster %(cluster)s"),
        {
            "task_definition": task_definition_arn,
            "cluster": settings.HOUNDIGRADE_ECS_CLUSTER_NAME,
        },
    )
    ecs.run_task(
        cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME,
        taskDefinition=task_definition_arn,
    )


def _build_container_definition(task_command):
    """
    Build a container definition to be used by an ecs task.

    Args:
        task_command (list): Command to insert into the definition.

    Returns (dict): Complete container definition.

    """
    container_definition = {
        "name": "Houndigrade",
        "image": f"{settings.HOUNDIGRADE_ECS_IMAGE_NAME}:"
        f"{settings.HOUNDIGRADE_ECS_IMAGE_TAG}",
        "cpu": 0,
        "memoryReservation": 256,
        "essential": True,
        "command": task_command,
        "environment": [
            {"name": "AWS_DEFAULT_REGION", "value": settings.AWS_SQS_REGION},
            {"name": "AWS_ACCESS_KEY_ID", "value": settings.AWS_SQS_ACCESS_KEY_ID},
            {
                "name": "AWS_SECRET_ACCESS_KEY",
                "value": settings.AWS_SQS_SECRET_ACCESS_KEY,
            },
            {
                "name": "RESULTS_QUEUE_NAME",
                "value": settings.HOUNDIGRADE_RESULTS_QUEUE_NAME,
            },
            {"name": "EXCHANGE_NAME", "value": settings.HOUNDIGRADE_EXCHANGE_NAME},
            {"name": "QUEUE_CONNECTION_URL", "value": settings.CELERY_BROKER_URL},
        ],
        "privileged": True,
        "logConfiguration": {
            "logDriver": "awslogs",
            "options": {
                "awslogs-create-group": "true",
                "awslogs-group": f"{settings.AWS_NAME_PREFIX}cloudigrade-ecs",
                "awslogs-region": settings.AWS_SQS_REGION,
            },
        },
    }
    if settings.HOUNDIGRADE_ENABLE_SENTRY:
        container_definition["environment"].extend(
            [
                {
                    "name": "HOUNDIGRADE_SENTRY_DSN",
                    "value": settings.HOUNDIGRADE_SENTRY_DSN,
                },
                {
                    "name": "HOUNDIGRADE_SENTRY_RELEASE",
                    "value": settings.HOUNDIGRADE_SENTRY_RELEASE,
                },
                {
                    "name": "HOUNDIGRADE_SENTRY_ENVIRONMENT",
                    "value": settings.HOUNDIGRADE_SENTRY_ENVIRONMENT,
                },
            ]
        )

    return container_definition
