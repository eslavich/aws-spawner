import asyncio
import logging
import json
from enum import Enum

from jupyterhub.spawner import Spawner
from jupyterhub.traitlets import ByteSpecification
from traitlets import (
    Bool,
    Dict,
    Integer,
    List,
    Unicode,
    Union,
    default,
    observe,
    validate,
)
import boto3


class InstanceState(Enum):
    PENDING = 0
    RUNNING = 16
    SHUTTING_DOWN = 32
    TERMINATED = 48
    STOPPING = 64
    STOPPED = 80

    @classmethod
    def from_instance(cls, instance):
        return cls(instance.state["Code"])

class VolumeState(Enum):
    CREATING = "creating"
    AVAILABLE = "available"
    IN_USE = "in-use"
    DELETING = "deleting"
    DELETED = "deleted"
    ERROR = "error"

    @classmethod
    def from_volume(cls, volume):
        return cls(volume.state)

# TODO: Should volume type be an enum?

class AwsSpawner(Spawner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.ec2 = boto3.resource("ec2")
        self.instance_id = None
        self.volume_ids_by_type = {}

    launch_template_id = Unicode(
        help="""
        AWS LaunchTemplateId that defines the instance created.
        """
    ).tag(config=True)

    instance_type = Unicode(
        help="""
        EC2 instance type that will be be created.  If absent, the launch template's default
        will be used.
        """
    ).tag(config=True)

    home_volume_snapshot_id = Unicode(
        help="""
        Snapshot used to create the user's home directory.
        """,
    ).tag(config=True)

    home_volume_device = Unicode(
        "/dev/sdf",
        help="""
        The device name of the volume containing the user's home directory.
        """,
    ).tag(config=True)

    env_volume_snapshot_id = Unicode(
        help="""
        Snapshot used to create the user's conda directory.
        """,
    ).tag(config=True)

    env_volume_device = Unicode(
        "/dev/sdg",
        help="""
        The device name of the volume containing the user's conda directory.
        """,
    ).tag(config=True)

    availability_zone = Unicode(
        help="""
        Availability zone of spawned instances and volumes
        """
    ).tag(config=True)

    terminate_on_stop = Bool(
        False,
        help="""
        If True, will terminate the user's instance on stop, otherwise it will merely stop the instance.
        """
    ).tag(config=True)

    delete_volumes_on_stop = Bool(
        False,
        help="""
        If True, will delete the user's volumes on stop, otherwise it'll leave the be.
        """
    ).tag(config=True)

    async def start(self):
        self.log.debug("Entered start")
        # TODO: Devise tag scheme with username

        user_data = self.get_user_data()

        self.log.debug("User data: %s", user_data)
        self.log.debug("User: %s", self.user)
        self.log.debug("Instance ID: %s", self.instance_id)

        instance = None
        if self.instance_id:
            try:
                self.log.debug("Attempting to load instance-id %s", self.instance_id)
                instance = self._get_instance(self.instance_id)
            except Exception:
                self.log.exception("Failed to load instance-id %s", self.instance_id)
                self.instance_id = None

        if instance:
            instance_state = InstanceState.from_instance(instance)
            self.log.debug("Instance %s exists and state is %s", instance.id, instance_state)

            if instance_state == InstanceState.SHUTTING_DOWN or instance_state == InstanceState.TERMINATED:
                instance = None
                self.instance_id = None
            elif instance_state == InstanceState.STOPPING or instance_state == InstanceState.STOPPED:
                await self._await_instance_state(instance, InstanceState.STOPPED)
                instance.start()
            # Other options are PENDING and RUNNING, both of which are acceptable

        if not instance:
            create_instances_kwargs = {
                "MinCount": 1,
                "MaxCount": 1,
                "LaunchTemplate": {"LaunchTemplateId": self.launch_template_id},
                "UserData": user_data
            }

            if self.instance_type:
                create_instances_kwargs["InstanceType"] = self.instance_type

            if self.availability_zone:
                create_instances_kwargs["Placement"] = {"AvailabilityZone": self.availability_zone}

            self.log.debug("Creating instance with %s", create_instances_kwargs)
            instance = self.ec2.create_instances(**create_instances_kwargs)[0]
            self.instance_id = instance.id
            self.log.debug("Created instance %s", instance)

        volumes_by_type = {}
        for volume_type in ["env", "home"]:
            volume = None
            if self.volume_ids_by_type.get(volume_type):
                volume_id = self.volume_ids_by_type[volume_id]
                try:
                    volume = self._get_volume(volume_id)
                except Exception:
                    self.log.exception("Failed to load volume-id %s", volume_id)
                    volume = None
                    self.volume_ids_by_type[volume_type] = None
                    volume_id = None

                if volume:
                    volume_state = VolumeState.from_volume(volume)
                    if volume_state == VolumeState.DELETING or volume_state == VolumeState.DELETED or volume_state == VolumeState.ERROR:
                        volume = None
                        self.volume_ids_by_type[volume_type] = None
                        volume_id = None
                    elif volume_state == VolumeState.IN_USE:
                        # TODO: This would be a weird state to get into, but we should handle it
                        assert volume.attachments[0]["InstanceId"] == instance.id
                        assert volume.attachments[0]["Device"] == getattr(self, f"{volume_type}_volume_device")
                    else:
                        # Other options are AVAILABLE and CREATING
                        # TODO: Handle this case.  Will have to snapshot and reload the volume in the correct AZ.
                        assert volume.availability_zone == instance.placement["AvailabilityZone"]

            if not volume:
                snapshot_id = getattr(self, f"{volume_type}_volume_snapshot_id")
                create_volume_kwargs = {
                    "AvailabilityZone": instance.placement["AvailabilityZone"],
                    "SnapshotId": snapshot_id
                }
                self.log.debug("Creating %s volume with %s", volume_type, create_volume_kwargs)
                volume = self.ec2.create_volume(**create_volume_kwargs)
                self.log.debug("Created %s %s", volume_type, volume)

            volumes_by_type[volume_type] = volume
            self.volume_ids_by_type[volume_type] = volume.id

        await self._await_instance_state(instance, InstanceState.RUNNING)

        for volume_type, volume in volumes_by_type.items():
            self.log.debug("Checking up on %s %s progress", volume_type, volume)
            if VolumeState.from_volume(volume) != VolumeState.IN_USE:
                await self._await_volume_state(volume, VolumeState.AVAILABLE)

        self.log.debug("Attaching volumes")
        for volume_type, volume in volumes_by_type.items():
            if VolumeState.from_volume(volume) != VolumeState.IN_USE:
                device = getattr(self, f"{volume_type}_volume_device")
                attach_response = instance.attach_volume(VolumeId=volume.id, Device=device)
                self.log.debug("The %s %s attached with device %s", volume_type, volume, attach_response["Device"])

        ip_address = instance.network_interfaces[0].private_ip_addresses[0]["PrivateIpAddress"]
        self.log.debug("Returning IP address %s, port %s", ip_address, self.port)
        return ip_address, self.port

    async def poll(self):
        self.log.debug("Entered poll")

        if self.instance_id is not None:
            try:
                instance = self._get_instance(self.instance_id)
                instance_state = InstanceState.from_instance(instance)
                if instance_state == InstanceState.RUNNING:
                    self.log.debug("Returning None")
                    return None
                else:
                    self.log.debug("Returning 0")
                    return 0
            except Exception:
                self.log.exception("Failed to fetch instance-id %s", self.instance_id)
                self.log.debug("Returning 0")
                return 0

        else:
            self.log.debug("Returning 0")
            return 0

    async def stop(self, now=False):
        self.log.debug("Entered stop")

        if self.instance_id is None:
            self.log.debug("No instance_id")
        else:
            if self.terminate_on_stop:
                self.log.debug("Terminating instance-id %s", self.instance_id)
                try:
                    instance = self._get_instance(self.instance_id)
                    instance.terminate()
                except Exception:
                    self.log.exception("Failed to fetch and terminate instance-id %s", self.instance_id)
                self.instance_id = None
            else:
                self.log.debug("Stopping instance-id %s", self.instance_id)
                try:
                    instance = self._get_instance(self.instance_id)
                    instance.stop()
                except Exception:
                    self.log.exception("Failed to fetch and stop instance-id %s", self.instance_id)
                    self.instance_id = None

        if self.delete_volumes_on_stop:
            for volume_type in ["home", "env"]:
                if self.volume_ids_by_type.get(volume_type):
                    self.log.debug("Deleting %s volume-id %s", volume_type, volume_id)
                    try:
                        volume = self._get_volume(volume_id)
                        volume_state = VolumeState.from_volume(volume)
                        if volume_state == VolumeState.IN_USE:
                            volume.detach_from_instance()
                        await self._await_volume_state(volume, VolumeState.AVAILABLE)
                        volume.delete()
                    except Exception:
                        self.log.exception("Failed to fetch and delete volume-id %s", self.volume_id)
                    self.volume_ids_by_type[volume_type] = None

        self.log.debug("Returning from stop")

    async def _await_instance_state(self, instance, target_state):
        await self._await_entity_state(instance, target_state, InstanceState.from_instance)

    async def _await_volume_state(self, volume, target_state):
        await self._await_entity_state(volume, target_state, VolumeState.from_volume)

    async def _await_entity_state(self, entity, target_state, state_getter):
        # TODO: This needs to time out instead of looping forever
        # TODO: Confirm that state is still the original state

        self.log.debug("Awaiting %s to transition from state %s to %s", entity, state_getter(entity), target_state)

        while state_getter(entity) != target_state:
            self.log.debug("Sleeping...")
            await asyncio.sleep(1)
            entity.reload()

        self.log.debug("%s successfully transitioned to state %s", entity, target_state)

    def get_state(self):
        self.log.debug("Getting state")

        state = super().get_state()

        state.update({
            "instance_id": self.instance_id,
            "volume_ids_by_type": self.volume_ids_by_type,
        })

        self.log.debug("Returning state: %s", state)

        return state

    def load_state(self, state):
        self.log.debug("Loading state: %s", state)

        super().load_state(state)

        self.instance_id = state.get("instance_id")
        self.volume_ids_by_type = state.get("volume_ids_by_type", {})

    def clear_state(self):
        self.log.debug("Clearing state")

        super().clear_state()

        self.instance_id = None
        self.volume_ids_by_type = {}

    def options_from_form(self, formdata):
        pass

    def get_user_data(self):
        env = self.get_env()

        user_data = {}
        user_data["env"] = env
        user_data["username"] = self.user.name

        return json.dumps(user_data)

    @default("options_form")
    def _options_form_default(self):
        return "<h1>aws-spawner demo</h1>"

    def _get_instance(self, instance_id):
        for instance in self.ec2.instances.filter(Filters=[{"Name": "instance-id", "Values": [instance_id]}]).limit(1):
            instance.load()
            return instance

        return None

    def _get_volume(self, volume_id):
        volume = self.ec2.Volume(volume_id)
        volume.load()
        return volume

    @default('env_keep')
    def _env_keep_default(self):
        # None of the hub instance's environment variables are relevant to the user's instance
        return []
