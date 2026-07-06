# Cloud Tools
A collection of command line tools for making development in AWS/Cumulus easier.

## Installation
Each command line tool is implemented as an installable python package using
pip console scripts. These can be installed with `pip` directly, but it is
advisable to install each tool to its own virtual environment to avoid 
clobbering dependencies.

### With UV (recommended)
[`uv`](https://docs.astral.sh/uv/) is a python package and project manager that
can be used to install and manage executable python packages into isolated 
environments. This is currently the recommended way to install tools from this 
repo, especially if you are already using uv elsewhere in your python 
development work.

To install the `destroy-cumulus` tool from Github over SSH:
```
uv tool install git+ssh://git@github.com/asfadmin/cloud-tools.git#subdirectory=destroy-cumulus
```

Or using HTTP:

```
uv tool install git+https://github.com/asfadmin/cloud-tools.git#subdirectory=destroy-cumulus
```

#### Updating
`uv tool` can detect if new changes have been merged to the Github repo and pull 
them in automatically using the `upgrade` functionality. Additionally, this will 
update any dependencies in the `uv tool` managed virtual environment to their 
latest compatible versions.

To upgrade all installed tools:
```
uv tool upgrade --all
```

To upgrade a specific tool:
```
uv tool upgrade destroy-cumulus
```

### With pipx

<details>
<summary>Expand for pipx instructions</summary>

[`pipx`](https://pypi.org/project/pipx/) is a tool for installing executable 
python packages to their own virtual environments. `uv tool` implements the same
functionality and should be prefered if you're already using `uv` on your system.

To install the `destroy-cumulus` tool from Github over SSH:
```
pipx install git+ssh://git@github.com/asfadmin/cloud-tools.git#subdirectory=destroy-cumulus
```

Or using HTTP:

```
pipx install git+https://github.com/asfadmin/cloud-tools.git#subdirectory=destroy-cumulus
```

#### Updating
`pipx` can detect if new changes have been merged to the Github repo and pull 
them in automatically using the `upgrade` functionality. Additionally, this will 
update any dependencies in the `pipx` managed virtual environment to their 
latest compatible versions.

To upgrade all installed tools:
```
pipx upgrade-all
```

To upgrade a specific tool:
```
pipx upgrade destroy-cumulus
```
</details>

### For local development
If you are developing changes to a tool, it is most convenient to install the
tool in editable mode so that changes to the code are instantly reflected in 
your installed version.

You can do this by cloning the repo and installing from a local path with the
`-e` flag to enable editable mode.
```
git clone git@github.com/asfadmin/cloud-tools.git
uv tool install -e cloud-tools/destroy-cumulus
```

*NOTE: Installing this way means you need to pull updates with git by hand. 
The usual method of updating the tool will not work.*
