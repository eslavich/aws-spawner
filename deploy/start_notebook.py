#!/usr/bin/env python3
import subprocess
import json
import os
from pathlib import Path
import pwd

HOME_DEVICE = "/dev/nvme1n1"
ENV_DEVICE = "/dev/nvme2n1"
ENV_PATH = "/opt/conda"

def get_user_data():
    return json.loads(subprocess.check_output(["curl", "http://169.254.169.254/latest/user-data"]))

def get_home_path(username):
    return f"/home/{username}"

def home_directory_exists(username):
    return Path(get_home_path(username)).exists()

def mount_home_directory(username):
    home_path = get_home_path(username)
    # TODO: Can we reboot the instance without losing these mounts?
    subprocess.check_call(["sudo", "mkdir", home_path])
    subprocess.check_call(["sudo", "mount", HOME_DEVICE, home_path])
    subprocess.check_call(["sudo", "chmod", "700", home_path])
    subprocess.check_call(["sudo", "chown", "--recursive", f"{username}:notebook-users", home_path])

def env_directory_exists():
    return Path(ENV_PATH).exists()

def mount_env_directory(username):
    subprocess.check_call(["sudo", "mkdir", ENV_PATH])
    subprocess.check_call(["sudo", "mount", ENV_DEVICE, ENV_PATH])
    subprocess.check_call(["sudo", "chmod", "775", ENV_PATH])

def user_exists(username):
    try:
        pwd.getpwnam(username)
    except KeyError:
        return False
    else:
        return True

def create_user(username):
    subprocess.check_call(["sudo", "adduser", "--no-create-home", "--shell", "/bin/bash", "-g", "notebook-users", username])

user_data = get_user_data()
username = user_data["username"]

if not user_exists(username):
    create_user(username)

if not home_directory_exists(username):
    mount_home_directory(username)

env = []
if "env" in user_data:
    for key, value in user_data["env"].items():
        env.append(f"{key}={value}")

command = f"cd {get_home_path(username)} && jupyter-labhub --ip=0.0.0.0"
args = ["sudo", "-u", username] + env + ["bash", "-l", "-c", command]
os.execv("/usr/bin/sudo", args)