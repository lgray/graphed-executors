#!/bin/sh
# Daemon-log evidence behind probe_surface_scratch.txt (run on the docker host after probe_surface_scratch.sh):
#  X-04: why a MY.SendCredential job idles on a pool without a credd/credmon (StarterLog: the starter refuses, the job requeues)
#  X-08: the apptainer command line the starter used for the Singularity configs (StarterLog)
echo "## surf-scr StarterLog, SendCredential"
docker exec surf-scr sh -c 'grep -h "SendCredential" /var/log/condor/StarterLog.slot* | tail -4'
echo "## surf-priv StarterLog, SendCredential"
docker exec surf-priv sh -c 'grep -h "SendCredential" /var/log/condor/StarterLog.slot* | tail -2'
echo "## surf-priv StarterLog, apptainer invocations (last 4 distinct)"
docker exec surf-priv sh -c 'grep -h "About to exec /usr/bin/singularity\|singularity exec\|Running job via singularity" /var/log/condor/StarterLog.slot* | sed "s/^.*(pid:[0-9]*) //" | sort -u | tail -6'
