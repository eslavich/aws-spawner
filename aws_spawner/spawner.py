from jupyterhub.spawner import Spawner

class AwsSpawner(Spawner):
    async def start(self):
        pass

    async def poll(self):
        pass

    async def stop(self):
        pass

    def get_state(self):
        pass

    def load_state(self, state):
        pass

    def clear_state(self, state):
        pass

    def options_from_form(self, formdata):
        pass

