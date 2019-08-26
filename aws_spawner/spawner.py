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
        # TODO: Devise tag scheme with username

        # TODO:
#         $ JUPYTERHUB_API_TOKEN=1 jupyter labhub
# [W 2019-08-23 22:18:49.662 SingleUserLabApp configurable:168] Config option `open_browser` not recognized by `SingleUserLabApp`.  Did you mean `browser`?
# [W 2019-08-23 22:18:49.663 SingleUserLabApp configurable:168] Config option `token` not recognized by `SingleUserLabApp`.
# Traceback (most recent call last):
#   File "/home/ec2-user/miniconda3/lib/python3.7/site-packages/traitlets/traitlets.py", line 528, in get
#     value = obj._trait_values[self.name]
# KeyError: 'oauth_client_id'

        # TODO: Pass environment variables to the instance from:
        # https://github.com/jupyterhub/jupyterhub/blob/master/jupyterhub/spawner.py#L669
        # Then need some way to pass this stuff to the instance...

        user_data = self.get_user_data()

        instance = self.ec2.create_instances(
            MinCount=1,
            MaxCount=1,
            LaunchTemplate={"LaunchTemplateId": self.launch_template_id},
            UserData=user_data
        )[0]

        self.instance_id = instance.id

        # TODO: This needs to be smarter, check for unexpected codes, etc
        # https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_InstanceState.html
        while instance.state["Code"] != 16:
            await asyncio.sleep(15)
            instance.reload()

        # TODO: Check "Status Checks" instead of just Instance State

        # self.ip_address = instance.network_interfaces[0].private_ip_addresses[0]["PrivateIpAddress"]
        self.ip_address = instance.public_ip_address

        return self.ip_address, self.port

    async def poll(self):
        # TODO: Return status 0 if not started yet

        if self.instance_id is not None:
            return None
        else:
            return 0

    async def stop(self, now=False):
        if self.instance_id is None:
            return

        # TODO: Does the record for the instance disappear if it's been terminated for a while?
        instance = self._get_instance(self.instance_id)
        instance.terminate()

        while instance.state["Code"] != 48:
            await asyncio.sleep(15)
            instance.reload()

        self.instance_id = None
        self.ip_address = None

    def get_state(self):
        state = super().get_state()

        state.update({
            "instance_id": self.instance_id,
            "ip_address": self.ip_address
        })

        return state

    def load_state(self, state):
        super().load_state(state)

        self.instance_id = state.get("instance_id")
        self.ip_address = state.get("ip_address")

    def clear_state(self):
        super().clear_state()

        # TODO: subclasses should call super

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