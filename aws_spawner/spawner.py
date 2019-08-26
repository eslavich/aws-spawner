import asyncio
import logging
import json

from jupyterhub.spawner import Spawner
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

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

class AwsSpawner(Spawner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.ec2 = boto3.resource("ec2")
        self.instance_id = None
        self.ip_address = None

    launch_template_id = Unicode(
        # TODO: Make the help more helpful
        help="""
        AWS LaunchTemplateId
        """
    ).tag(config=True)

    async def start(self):
        LOGGER.info("Entered start")
        # TODO: Devise tag scheme with username

        LOGGER.info("Looking for volume")

        user_data = self.get_user_data()

        LOGGER.info("User data: %s", user_data)

        instance = self.ec2.create_instances(
            MinCount=1,
            MaxCount=1,
            LaunchTemplate={"LaunchTemplateId": self.launch_template_id},
            UserData=user_data
        )[0]

        self.instance_id = instance.id

        LOGGER.info("Created instance_id %s", self.instance_id)

        # TODO: This needs to be smarter, check for unexpected codes, etc
        # https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_InstanceState.html
        while instance.state["Code"] != 16:
            LOGGER.info("Code is %s", instance.state["Code"])
            await asyncio.sleep(1)
            instance.reload()

        # TODO: Check "Status Checks" instead of just Instance State

        self.ip_address = instance.network_interfaces[0].private_ip_addresses[0]["PrivateIpAddress"]
        #self.ip_address = instance.public_ip_address

        LOGGER.info("Returning IP address %s, port %s", self.ip_address, self.port)

        return self.ip_address, self.port

    async def poll(self):
        LOGGER.debug("Entered poll")
        # TODO: Return status 0 if not started yet

        if self.instance_id is not None:
            LOGGER.debug("Returning None")
            return None
        else:
            LOGGER.debug("Returning 0")
            return 0

    async def stop(self, now=False):
        LOGGER.debug("Entered stop")

        if self.instance_id is None:
            LOGGER.debug("No instance_id, returning from stop")
            return

        LOGGER.debug("Terminating instance_id %s", self.instance_id)
        instance = self._get_instance(self.instance_id)
        if not instance:
            LOGGER.warning("Missing instance %s", self.instance_id)
        instance.terminate()

        while instance.state["Code"] != 48:
            LOGGER.debug("Code is %s", instance.state["Code"])
            await asyncio.sleep(1)
            instance.reload()

        self.instance_id = None
        self.ip_address = None

        LOGGER.debug("Returning from stop")

    def get_state(self):
        LOGGER.debug("Getting state")

        state = super().get_state()

        state.update({
            "instance_id": self.instance_id,
            "ip_address": self.ip_address
        })

        LOGGER.debug("Returning state: %s", state)

        return state

    def load_state(self, state):
        LOGGER.debug("Loading state: %s", state)

        super().load_state(state)

        self.instance_id = state.get("instance_id")
        self.ip_address = state.get("ip_address")

    def clear_state(self):
        LOGGER.debug("Clearing state")

        super().clear_state()

        self.instance_id = None
        self.ip_address = None

    def options_from_form(self, formdata):
        pass

    def get_user_data(self):
        env = self.get_env()

        user_data = {}
        user_data["env"] = env

        return json.dumps(user_data)

    @default("options_form")
    def _options_form_default(self):
        return "<h1>HEY I'M SO EXCITED TO BE HERE</h1>"

    def _get_instance(self, instance_id):
        for instance in self.ec2.instances.filter(Filters=[{"Name": "instance-id", "Values": [instance_id]}]).limit(1):
            return instance

        return None

    @default('env_keep')
    def _env_keep_default(self):
        # None of the hub instance's environment variables are relevant to the user's instance
        return []
