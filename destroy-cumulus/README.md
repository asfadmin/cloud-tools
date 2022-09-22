# Destroy Cumulus
Manually tear down AWS resources associated with cumulus.

This should generally be used as a last resort to find resources which failed
to be deleted by terraform, or became orphaned somehow. This script is pretty
'dumb' in the sense that it is not necessarily aware of destruction order or
how to wait for resources to be destroyed before initiating destruction of
dependent resources. It may need to be invoked several times at sufficient
intervals for everything to be destroyed.

Always double check the destruction plan to make sure no undesired resources
will be destroyed.
