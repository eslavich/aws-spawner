import asyncio
import logging
import json

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


class AwsSpawner(Spawner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.ec2 = boto3.resource("ec2")
        self.instance_id = None
        self.ip_address = None

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

    home_volume_size = ByteSpecification(
        help="""
        Size of the EBS volume that will be created for the user's home directory.
        """,
    ).tag(config=True)

    home_snapshot_id = Unicode(
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

    availability_zone = Unicode(
        help="""
        Availability zone of spawned instances and volumes
        """
    ).tag(config=True)

    async def start(self):
        self.log.debug("Entered start")
        # TODO: Devise tag scheme with username

        user_data = self.get_user_data()

        self.log.debug("User data: %s", user_data)
        self.log.debug("User: %s", self.user)

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
        self.ip_address = instance.network_interfaces[0].private_ip_addresses[0]["PrivateIpAddress"]
        self.log.debug("Created instance_id %s", self.instance_id)

        create_volume_kwargs = {
            "AvailabilityZone": instance.placement["AvailabilityZone"],
        }

        if self.home_volume_size:
            create_volume_kwargs["Size"] = int(self.home_volume_size / (1024 * 1024 * 1024))
        if self.home_snapshot_id:
            create_volume_kwargs["SnapshotId"] = self.home_snapshot_id

        self.log.debug("Creating volume with %s", create_volume_kwargs)
        volume = self.ec2.create_volume(**create_volume_kwargs)
        self.volume_id = volume.id
        self.log.debug("Created volume id %s", volume.id)

        # TODO: This needs to be smarter, check for unexpected codes, etc
        # https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_InstanceState.html
        while instance.state["Code"] != 16:
            self.log.debug("Code is %s", instance.state["Code"])
            await asyncio.sleep(1)
            instance.reload()

        # TODO: Check "Status Checks" instead of just Instance State

        volume.reload()
        while volume.state != "available":
            self.log.debug("Volume state is %s", volume.state)
            await asyncio.sleep(1)
            volume.reload()

        self.log.debug("Attaching volume")
        attach_response = instance.attach_volume(VolumeId=volume.id, Device=self.home_volume_device)
        self.log.debug("Volume attached with device %s", attach_response["Device"])

        self.log.debug("Returning IP address %s, port %s", self.ip_address, self.port)

        return self.ip_address, self.port

    async def poll(self):
        self.log.debug("Entered poll")
        # TODO: Return status 0 if not started yet

        if self.instance_id is not None:
            self.log.debug("Returning None")
            return None
        else:
            self.log.debug("Returning 0")
            return 0

    async def stop(self, now=False):
        self.log.debug("Entered stop")

        if self.instance_id is None:
            self.log.debug("No instance_id")
        else:
            self.log.debug("Terminating instance_id %s", self.instance_id)
            instance = self._get_instance(self.instance_id)
            if not instance:
                self.log.warning("Missing instance %s", self.instance_id)
            else:
                instance.terminate()

        if self.volume_id is None:
            self.log.debug("No volume_id")
        else:
            self.log.debug("Deleting volume %s", self.volume_id)
            volume = self._get_volume(self.volume_id)
            if not volume:
                self.log.warning("Missing volume %s", self.volume_id)
            else:
                while volume.state != "available":
                    self.log.debug("Volume state is %s", volume.state)
                    await asyncio.sleep(1)
                    volume.reload()

                volume.delete()

        self.instance_id = None
        self.ip_address = None
        self.volume_id = None

        self.log.debug("Returning from stop")

    def get_state(self):
        self.log.debug("Getting state")

        state = super().get_state()

        state.update({
            "instance_id": self.instance_id,
            "ip_address": self.ip_address,
            "volume_id": self.volume_id,
        })

        self.log.debug("Returning state: %s", state)

        return state

    def load_state(self, state):
        self.log.debug("Loading state: %s", state)

        super().load_state(state)

        self.instance_id = state.get("instance_id")
        self.ip_address = state.get("ip_address")
        self.volume_id = state.get("volume_id")

    def clear_state(self):
        self.log.debug("Clearing state")

        super().clear_state()

        self.instance_id = None
        self.ip_address = None
        self.volume_id = None

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
        return "<h1>HEY I'M SO EXCITED TO BE HERE</h1>"

    def _get_instance(self, instance_id):
        for instance in self.ec2.instances.filter(Filters=[{"Name": "instance-id", "Values": [instance_id]}]).limit(1):
            return instance

        return None

    def _get_volume(self, volume_id):
        return self.ec2.Volume(volume_id)

    @default('env_keep')
    def _env_keep_default(self):
        # None of the hub instance's environment variables are relevant to the user's instance
        return []
