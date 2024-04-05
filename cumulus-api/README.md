# Cumulus API
A tool to query the cumulus API lambda directly via boto3.

This allows you to access cumulus API functions easily without needing to
launchpad authentication provided you have AWS credentials to the account.
Additionally, this enables you to query the cumulus API in sandbox accounts
without needing to go through the NASA VPN / SSH bastion.

## Commands

### Curl
The `cumulus curl` command mimics certain elements of `curl` allowing you to
access the cumulus API in a familiar way.

### Deploy
The `cumulus deploy` command will update or create providers, collections and
rules from JSON files discovered within a directory. This functionality comes
from how providers, collections and rules were originally handled in CIRRUS.
