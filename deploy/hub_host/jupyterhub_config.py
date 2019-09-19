c.JupyterHub.authenticator_class = "dummy"
c.DummyAuthenticator.password = "test"
c.JupyterHub.hub_connect_ip = "172.31.45.91"
#c.JupyterHub.hub_ip = "54.224.124.136"
#c.JupyterHub.hub_port = 8081
c.JupyterHub.spawner_class = 'aws_spawner'
#c.Spawner.cmd = ['jupyterhub-singleuser']
c.Spawner.debug = True
c.Spawner.http_timeout = 1200
c.Spawner.port = 8888
c.Spawner.start_timeout = 1200
c.AwsSpawner.instance_type = "t3.large"
c.AwsSpawner.launch_template_id = "lt-07df94397c1146b8b"
c.AwsSpawner.home_volume_snapshot_id = "snap-0240c6612c81b1b2f"
c.AwsSpawner.home_volume_device = "/dev/sdf"
c.AwsSpawner.env_volume_snapshot_id = "snap-0240c6612c81b1b2f"
c.AwsSpawner.env_volume_device = "/dev/sdg"
c.AwsSpawner.availability_zone = "us-east-1a"
