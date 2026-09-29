#!/bin/sh
# Drive probe_surface_scratch.py across EP configurations (run on the docker host):
#   surf-scr  = htcondor/mini, unprivileged (the starter cannot bind-mount)
#   surf-priv = htcondor/mini, --privileged (MOUNT_UNDER_SCRATCH and apptainer work); /opt/img = a sandbox image made by
#     copying the container's /usr,/bin,/lib,/lib64,/sbin + passwd/group/hosts into /opt/img0, then `apptainer build --sandbox /opt/img /opt/img0`
# Each config is a file in /etc/condor/config.d/99-surf followed by condor_reconfig (every knob varied here is read by
# the condor_starter, which each job starts afresh).
set -u
P=/probes/condor_surface/probe_surface_scratch.py
run() { # container label jobs config-text
  docker exec "$1" sh -c "printf '%s\n' \"$4\" > /etc/condor/config.d/99-surf && condor_reconfig >/dev/null && sleep 5"
  echo "## config $2 on $1: $(echo "$4" | tr '\n' ';')"
  docker exec -u submituser -w /home/submituser "$1" python3 $P "$2" "$3"
}
run surf-scr  A-unpriv-default        plain,proxy,cred,tmpin "# defaults"
run surf-scr  B-unpriv-nested-false   plain,proxy          "STARTER_NESTED_SCRATCH = false"
run surf-scr  B2-unpriv-sing-attr-only sing                "# defaults: MY.SingularityImage set, SINGULARITY_JOB not configured"
run surf-priv C-priv-default          plain,proxy,cred,tmpin "# defaults"
run surf-priv D-priv-mus-empty        plain,tmpin          'MOUNT_UNDER_SCRATCH = ""'
run surf-priv E-priv-mus-devshm       plain                'MOUNT_UNDER_SCRATCH = "/tmp,/var/tmp,/dev/shm"'
run surf-priv F-priv-nested-false     plain,proxy,tmpin    "STARTER_NESTED_SCRATCH = false"
run surf-priv F2-priv-sing-srv-nested-false sing,singall  "SINGULARITY_JOB = !isUndefined(TARGET.SingularityImage)
SINGULARITY_IMAGE_EXPR = TARGET.SingularityImage
SINGULARITY_TARGET_DIR = /srv
STARTER_NESTED_SCRATCH = false"
run surf-priv G-priv-sing             sing,singall           "SINGULARITY_JOB = !isUndefined(TARGET.SingularityImage)
SINGULARITY_IMAGE_EXPR = TARGET.SingularityImage"
run surf-priv H-priv-sing-srv         sing,singall                 "SINGULARITY_JOB = !isUndefined(TARGET.SingularityImage)
SINGULARITY_IMAGE_EXPR = TARGET.SingularityImage
SINGULARITY_TARGET_DIR = /srv"
