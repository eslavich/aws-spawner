# CRDS Ansible scripts

So you wanna install the CRDS server?  Herein lie the Ansible scripts that will get the job done for you.  These scripts remote-control the CRDS VMs from a laptop; some setup is required, but once configured, you'll be able to make an install without manually logging in to the VM.

## Setup

### Install and configure Ansible

The first step is to install Ansible itself.  Full instructions may be found [here](https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html), but on macOS the package is available via homebrew:

```console
$ brew install ansible
```

or pip:

```console
$ pip install --user ansible
```

Once installed, the `ansible` command should be available:

```console
$ ansible --version
ansible 2.6.4
  config file = /Users/eslavich/.ansible.cfg
  configured module search path = ['/Users/eslavich/.ansible/plugins/modules', '/usr/share/ansible/plugins/modules']
  ansible python module location = /sw/lib/python3.7/site-packages/ansible
  executable location = /sw/bin/ansible
  python version = 3.7.2 (default, Jan 10 2019, 12:15:35) [Clang 10.0.0 (clang-1000.11.45.5)]
```

Ansible doesn't require a configuration file, but it saves some typing to define defaults in an ansible.cfg.  At a minimum, consider adding the following to ansible/ansible.cfg in your local copy of crds-server:

```yml
[defaults]
inventory = inventory.yml

[ssh_connection]
pipelining = True
```

The `inventory` setting specifies the default list of hostnames that Ansible will operate on, and the `pipelining` setting allows Ansible to combine multiple operations over a single SSH connection.

### Authentication

Ansible isn't able to display the VM's authentication prompt (Duo Push and password), and anyway you wouldn't want to enter your password for each individual SSH connection that Ansible makes.  Luckily, Kerberos authentication offers an alternative that doesn't require user interaction beyond simply logging in to your laptop.  To enable Kerberos authentication and ticket forwarding (needed to switch to the `crds` service account) for STScI VMs, add the following to `~/.ssh/config`:

```
Host *.stsci.edu
    GSSAPIAuthentication=yes
    GSSAPIDelegateCredentials=yes
    PreferredAuthentications=gssapi-with-mic,hostbased,publickey,keyboard-interactive,password
```

Now you should be able to log in to a CRDS VM without challenge:

```console
$ ssh your-username@dlhstcrds.stsci.edu
```

Ansible will also need to be able to switch to the `crds` user, which is the service account that runs the CRDS server code.  The `sudo su - crds` command is not an option here, because it also forces the user to do battle with Duo Push.  There is an analogous command, `ksu crds`, which will get the job done, but it requires that your username be whitelisted in a file in the `crds` user's home directory.  Edit `/home/crds/.k5login` on each VM that you might wish to install, and add your username to the list:

```
your-username@STSCI.EDU
```

Note that `STSCI.EDU` must be in ALL CAPS.

Exit back to your own user and confirm that the operation was successful by running `ksu crds`:

```console
$ ksu crds
Authenticated your-username@STSCI.EDU
Account crds: authorization for your-username@STSCI.EDU successful
Changing uid to crds (1258)
```

#### Ticket expiration

In the middle of an otherwise blissful day of successfully authenticating with Kerberos, you might discover that your logins suddenly start to fail.  Before throwing your laptop out the window, try renewing your Kerberos ticket by running the following command on the offending laptop:

```console
$ kinit -R
```

### GitHub credentials

You'll need to provide GitHub credentials to Ansible so that it can fetch from crds-server, which is a private repository.  Follow [these instructions](https://help.github.com/en/articles/creating-a-personal-access-token-for-the-command-line) to generate an access token with permissions to control private repositories.

The scripts are configured to read your GitHub username and token from environment variables.  Set `GIT_USERNAME` and `GIT_TOKEN` appropriately.

## Running an install

With setup out of the way, we can now run the install.yml playbook!  The playbook has two required variables, `target` and `branch`, which specify the target hostname and client and server branch/tag to install.  Here is a sample invocation to install the client and server code at tag 7.4.0 on dlhstcrds.stsci.edu:

```console
$ ansible-playbook install.yml --extra-vars "target=dlhstcrds.stsci.edu branch=7.4.0"
```

The script will commence its work, ideally reporting success after each step.  Adding a `-v` flag to the command will show console output from each command.

**CAUTION:** Ansible is perfectly happy to perform parallel installs, so it is possible to install to all VMs simultaneously (in fact, this is Ansible's default behavior).  We've added the `target` variable to help prevent mistakes, but you probably never want to specify `target=stsci`.

### Inspecting logs

Many of the tasks in the current (2019-08-16) playbooks invoke long-winded scripts, and Ansible is not able to display output until a task is completed.  If you want to see progress, it is possible to tail the output on the instance itself.  Login and change to the `crds` user, and look for log files in `/crds/data1/persistent_local/ansible_logs`.
