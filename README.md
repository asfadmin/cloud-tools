# Cloud Tools
A collection of command line tools for making development in AWS/Cumulus easier.

## Installation
Each command line tool is implemented as an installable python package using
pip console scripts. These can be installed with `pip` directly, but it is
advisable to use [`pipx`](https://pypi.org/project/pipx/) instead to keep
dependencies separate and out of the global python environment.

For example to install the `destroy-cumulus` tool from Github:
```
pipx install git+ssh://git@github.com/<user>/<repo>.git#subdirectory=destroy-cumulus
```

Or from local clone:
```
git clone git@github.com/<user>/<repo>.git
pipx install -e cloud-tools/destroy-cumulus
```
Note that the use of `-e` is optional, but will install the package in editable
mode allowing you to see changes to the source repo (such as those created by
`git pull`) without needing to re-install the package.
