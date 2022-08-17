"""Utility functions for Azure models and use cases."""
import logging

from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from api import error_codes
from api.clouds.azure.models import (
    AzureCloudAccount,
    AzureInstance,
    AzureInstanceEvent,
    AzureMachineImage,
)
from api.models import (
    CloudAccount,
    Instance,
    InstanceEvent,
    MachineImage,
)


logger = logging.getLogger(__name__)


def create_azure_cloud_account(
    user,
    subscription_id,
    platform_authentication_id,
    platform_application_id,
    platform_source_id,
):
    """
    Create AzureCloudAccount for the customer user.

    This function may raise ValidationError if certain verification steps fail.

    We call CloudAccount.enable after creating it, and that effectively verifies Azure
    permission. If that fails, we must abort this creation.
    That is why we put almost everything here in a transaction.atomic() context.

    Args:
        user (api.User): user to own the CloudAccount
        subscription_id (str): UUID of the customer subscription
        platform_authentication_id (str): Platform Sources' Authentication object id
        platform_application_id (str): Platform Sources' Application object id
        platform_source_id (str): Platform Sources' Source object id

    Returns:
        CloudAccount the created cloud account.

    """
    logger.info(
        _(
            "Creating an AzureCloudAccount. "
            "account_number=%(account_number)s, "
            "org_id=%(org_id)s, "
            "subscription_id=%(subscription_id)s, "
            "platform_authentication_id=%(platform_authentication_id)s, "
            "platform_application_id=%(platform_application_id)s, "
            "platform_source_id=%(platform_source_id)s"
        ),
        {
            "account_number": user.account_number,
            "org_id": user.org_id,
            "subscription_id": subscription_id,
            "platform_authentication_id": platform_authentication_id,
            "platform_application_id": platform_application_id,
            "platform_source_id": platform_source_id,
        },
    )

    with transaction.atomic():
        try:
            azure_cloud_account = AzureCloudAccount.objects.create(
                subscription_id=subscription_id
            )
        except IntegrityError:
            # create can raise IntegrityError if the given
            # subscription_id already exists in an account
            error_code = error_codes.CG1005
            error_code.notify(user.account_number, user.org_id, platform_application_id)
            raise ValidationError({"subscription_id": error_code.get_message()})

        cloud_account = CloudAccount.objects.create(
            user=user,
            content_object=azure_cloud_account,
            platform_application_id=platform_application_id,
            platform_authentication_id=platform_authentication_id,
            platform_source_id=platform_source_id,
        )

        # This enable call *must* be inside the transaction because we need to
        # know to rollback the transaction if anything related to enabling fails.
        if not cloud_account.enable(disable_upon_failure=False):
            # Enabling of cloud account failed, rolling back.
            transaction.set_rollback(True)
            raise ValidationError(
                {
                    "is_enabled": "Could not enable cloud account. "
                    "Please check your credentials."
                }
            )

    return cloud_account


def create_new_machine_images(vms_data):
    """
    Create AzureMachineImage objects that have not been seen before.

    Model AzureMachineImage:
    resource_id (varchar)                  vm.storage_profile.image_reference.sku
    azure_marketplace_image (boolean)
    region (varchar)

    Returns:
        list: A list of image ids that were added to the database
    """
    log_prefix = "create_new_machine_image"

    seen_azure_skus = {vm.storage_profile.image_reference.sku for vm in vms_data}
    known_skus = {
        azure_machine_image.sku
        for azure_machine_image in AzureMachineImage.objects.all()
    }

    new_skus = []
    for vm in vms_data:
        sku = vm.storage_profile.image_reference.sku
        azure_marketplace_image = False  # AAB - Revisit
        region = ""
        if sku not in list(known_skus):
            logger.info(
                _("%(prefix)s: Saving new Azure Machine Image sku: %(sku)s"),
                {"prefix": log_prefix, "sku": sku},
            )
            resource_id = sku
            azure_marketplace_image = False
            region = "TBD"
            inspection_json = {}
            name = sku
            rhel_detected_by_tag = False
            status = MachineImage.PENDING
            is_encrypted = True if vm.os_disk.encryption_settings else False
            openshift_detected = False
            architecture = "none"
            image, new = save_new_azure_machine_image(
                sku,
                azure_marketplace_image,
                region,
                inspection_json,
                name,
                is_encrypted,
                status,
                openshift_detected,
                rhel_detected_by_tag,
                architecture,
            )
            if new:
                new_skus.append(sku)

    return new_skus


def save_new_azure_machine_image(
    resource_id,
    azure_marketplace_image,
    region,
    inspection_json,
    name,
    is_encrypted,
    status,
    openshift_detected,
    rhel_detected_by_tag,
    architecture,
):
    """
        Save a new AzureMachineImage image object.

        Model AzureMachineImage:
        resource_id (varchar)                  vm.storage_profile.image_reference.sku
        azure_marketplace_image (boolean)
        region (varchar)

        Model MachineImage:
        object_id
        inspection_json
        is_encrypted                            if vm.os_disk.encryption_settings
        status
        openshift_detected
        name
        content_type_id
        rhel_detected_by_tag
        architecture

    Args:
        resource_id (str): The Azure image identifier
        azure_marketplace_image (boolean): True if the image is from the marketplace
        region (str): Region where the image was found"""

    platform = "none"
    status = MachineImage.PENDING
    with transaction.atomic():
        azuremachineimage, created = AzureMachineImage.objects.get_or_create(
            resource_id=sku,
            azure_marketplace_image=azure_marketplace_image,
            region=region,
        )

        if created:
            logger.info(
                _("save_new_azure_machine_image created %(azuremachineimage)s"),
                {"azuremachineimage": azuremachineimage},
            )
            machineimage = MachineImage.objects.create(
                name=name,
                status=status,
                rhel_detected_by_tag=rhel_detected_by_tag,
                is_encrypted=is_encrypted,
                openshift_detected=openshift_detected,
                content_object=azuremachineimage,
                architecture=architecture,
            )
            logger.info(
                _("save_new_azure_machine_image created %(machineimage)s"),
                {"machineimage": machineimage},
            )
        azuremachineimage.machine_image.get()

    return azuremachineimage, created


def create_initial_azure_instance_events(account, vms_data):
    """
    Create AzureInstance and AzureInstanceEvent the first time we see a vm.

    Model AzureInstance:
    resource_id (varchar)               vm.id
    region (varchar)

    Model AzureInstanceEvent:
    instance_type (varchar)

    Args:
        account (CloudAccount): The account that owns the vm that spawned
            the data for these InstanceEvents.
        vms_data (dict): Dict of discovereds vms for the account subscription.
    """


@transaction.atomic()
def save_instance(account, vm_data, region):
    """
    Create or Update the instance object for the Azure vm

    Args:
        account (CloudAccount): The account that owns the vm that spawned
            the data for this Instance.
        vm_data (dict): Dict of the details of this vm
        region (str): Azure region

    Returns:
        AzureInstance: Object representing the saved instance.
    """


def save_instance_events(azureinstance, vm_data, events=None):
    """
    Save provided events, and create the instance object if it does not exist.

    Args:
        azureinstance (AzureInstance): The Instnace associated with these
            InstanceEvents.
        vm_data (dict): Dictionary containing instance information.
        region (str): Azure region
        events(list[dict]): List of dicts representing Evnts to be saved.

    Retunrs:
        AzureInstance: Object representing the saved instnace.
    """


def get_instance_event_type(vm):
    """
    Return the InstanceEvent type for the vm specified.

    if vm["running"]   true if vm.instnace_view.statuses[].status.code is PowerState/running
    """
    if vm and vm["running"]:
        return InstanceEvent.TYPE.power_on
    else:
        return InstanceEvent.TYPE.power_off


"""
api_instance
    object_id
    cloud_account_id
    content_type_id
    machine_image_id

 api_instance_definition
    instance_type               Standard_D4ds_v4
    memory_mib                  15258
    vcpu                        4
    json_definition             {"{\"additional_properties\": {}, \"resource_type\": \"virtualMachines\", \"name\": \"Standard_D4ds_v4\", \"tier\": \"Standard\", \"size\": \"D4ds_v4\", \"family\": \"standardDDSv4Family\", ...}
    cloud_type                  "azure"

api_instanceevent
    object_id
    event_type
    occurred_at
    content_type_id
    instance_id

[{'id': '/subscriptions/c2b810d4-e83c-4df5-a728-f1301dd78561/resourceGroups/BRADS-TEST-RESOURCE-GROUP/providers/Microsoft.Compute/virtualMachines/brad-rhdir1-useast-zone1-vm1-20220815',
  'name': 'brad-rhdir1-useast-zone1-vm1-20220815',
  'resourceGroup': 'BRADS-TEST-RESOURCE-GROUP',
  'running': False,
  'instance_view': {'additional_properties': {},
   'platform_update_domain': None,
   'platform_fault_domain': None,
   'computer_name': None,
   'os_name': None,
   'os_version': None,
   'hyper_v_generation': None,
   'rdp_thumb_print': None,
   'vm_agent': None,
   'maintenance_redeploy_status': None,
   'disks': None,
   'extensions': None,
   'vm_health': None,
   'boot_diagnostics': None,
   'assigned_host': None,
   'statuses': [<azure.mgmt.compute.v2022_03_01.models._models_py3.InstanceViewStatus at 0x1096bda30>,
    <azure.mgmt.compute.v2022_03_01.models._models_py3.InstanceViewStatus at 0x1096bda60>],
   'patch_status': None},
  'license_type': None,
  'vm_size': 'Standard_B1ls',
  'hardware_profile': {'additional_properties': {},
   'vm_size': 'Standard_B1ls',
   'vm_size_properties': None},
  'storage_profile': {'additional_properties': {},
   'image_reference': <azure.mgmt.compute.v2022_03_01.models._models_py3.ImageReference at 0x1096a58b0>,
   'os_disk': <azure.mgmt.compute.v2022_03_01.models._models_py3.OSDisk at 0x1096a5910>,
   'data_disks': []},
  'os_profile': {'additional_properties': {},
   'computer_name': 'brad-rhdir1-useast-zone1-vm1-20220815',
   'admin_username': 'brasmith',
   'admin_password': None,
   'custom_data': None,
   'windows_configuration': None,
   'linux_configuration': <azure.mgmt.compute.v2022_03_01.models._models_py3.LinuxConfiguration at 0x1096a5a00>,
   'secrets': [],
   'allow_extension_operations': True,
   'require_guest_provision_signal': True},
  'linux_configuration': {'additional_properties': {'enableVMAgentPlatformUpdates': False},
   'disable_password_authentication': False,
   'ssh': None,
   'provision_vm_agent': True,
   'patch_settings': <azure.mgmt.compute.v2022_03_01.models._models_py3.LinuxPatchSettings at 0x1096a59a0>},
  'network_profile': {'additional_properties': {},
   'network_interfaces': [<azure.mgmt.compute.v2022_03_01.models._models_py3.NetworkInterfaceReference at 0x1096a5b50>],
   'network_api_version': None,
   'network_interface_configurations': None},
  'diagnostics_profile': {'additional_properties': {},
   'boot_diagnostics': <azure.mgmt.compute.v2022_03_01.models._models_py3.BootDiagnostics at 0x1096a5af0>},
  'os_disk': {'additional_properties': {},
   'os_type': 'Linux',
   'encryption_settings': None,
   'name': 'brad-rhdir1-useast-zone1-vm1-20220815_OsDisk_1_7d50783ae44e4bc09f0ce7d717f87fe0',
   'vhd': None,
   'image': None,
   'caching': 'ReadWrite',
   'write_accelerator_enabled': None,
   'diff_disk_settings': None,
   'create_option': 'FromImage',
   'disk_size_gb': None,
   'managed_disk': <azure.mgmt.compute.v2022_03_01.models._models_py3.ManagedDiskParameters at 0x1096a58e0>,
   'delete_option': 'Delete'},
  'managed_disk': {'additional_properties': {},
   'id': '/subscriptions/c2b810d4-e83c-4df5-a728-f1301dd78561/resourceGroups/brads-test-resource-group/providers/Microsoft.Compute/disks/brad-rhdir1-useast-zone1-vm1-20220815_OsDisk_1_7d50783ae44e4bc09f0ce7d717f87fe0',
   'storage_account_type': None,
   'disk_encryption_set': None,
   'security_profile': None},
  'image': {'additional_properties': {},
   'id': None,
   'publisher': 'RedHat',
   'offer': 'RHEL',
   'sku': '82gen2',
   'version': 'latest',
   'exact_version': '8.2.2022031402',
   'shared_gallery_image_id': None,
   'community_gallery_image_id': None}}]
"""
