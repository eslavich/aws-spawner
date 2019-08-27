#!/usr/bin/env python3
import subprocess
import json
import os
from pathlib import Path
import pwd

def get_user_data():
    return json.loads(subprocess.check_output(["curl", "http://169.254.169.254/latest/user-data"]))

def home_directory_exists(username):
    return Path(f"/home/{username}").exists()

def mount_home_directory(username):
    file_result = subprocess.check_output(["sudo", "file",  "-s", "/dev/nvme1n1"]).strip()
    assert file_result.startswith("/dev/nvme1n1:")
    file_result = file_result[len("/dev/nvme1n1:"):].strip()
    if file_result == "data":
        subprocess.check_call(["sudo", "mkfs", "-t", "xfs", "/dev/nvme1n1"])
    subprocess.check_call(["sudo", "mkdir", f"/home/{username}"])
    subprocess.check_call(["sudo", "mount", "/dev/nvme1n1", f"/home/{username}"])
    subprocess.check_call(["sudo", "chmod", "700", f"/home/{username}"])
    subprocess.check_call(["sudo", "chown", "--recursive", "eslavich:eslavich", f"/home/{username}"])

def user_exists(username):
    try:
        pwd.getpwnam(username)
    except KeyError:
        return False
    else:
        return True

def create_user(username):
    subprocess.check_call(["sudo", "adduser", "--no-create-home", "--shell", "/bin/bash", "--user-group", username])

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

command = f"cd /home/{username} && jupyter-labhub"
args = ["sudo", "-u", username] + env + ["bash", "-l", "-c", command]
os.execv("/usr/bin/sudo", args)