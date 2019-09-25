#!/usr/bin/env python
import sys
import os

prompt = sys.argv[1]

if prompt.startswith("Username"):
    print(os.environ["GIT_USERNAME"])
    exit(0)
elif prompt.startswith("Password"):
    print(os.environ["GIT_TOKEN"])
    exit(0)
else:
    exit(1)
