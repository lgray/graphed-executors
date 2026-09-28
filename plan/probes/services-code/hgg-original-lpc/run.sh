#!/bin/bash
# m69a premise probe at LPC: higgs_dna (git ref, --no-deps) + pull_files.py in a scratch venv inside the coffea image; the
# ORIGINAL processor on entries [0, 20000) of the first GluGluH 2024 amcatnlo file over xrootd. Login node only, no submission.
set -x
IMAGE=/cvmfs/unpacked.cern.ch/registry.hub.docker.com/coffeateam/coffea-almalinux9-noml:2026.9.0-py3.12
REF=d17930519cafd8eec06e74e4e9fb7add3cf62b5a
# $1 = the scratch dir the caller unpacked this tarball into, $2 = the xrootd URL
T=$1 URL=$2
cd "$T"
# site-check-lpc bind set minus the condor-config binds (no submission here)
export APPTAINER_BINDPATH=/uscmst1b_scratch,/cvmfs,/cvmfs/grid.cern.ch/etc/grid-security:/etc/grid-security
export X509_USER_PROXY=$HOME/x509up_u13225
apptainer exec --pwd "$T" "$IMAGE" /bin/bash -c "
set -x
python -m venv --system-site-packages $T/venv
time $T/venv/bin/pip install -q --no-deps 'higgs-dna @ git+https://gitlab.cern.ch/HiggsDNA-project/HiggsDNA.git@$REF' 2>&1 | grep -v notice
$T/venv/bin/pull_files.py --target GoldenJSON 2>&1 | grep -E 'Collisions24|ERROR' | head -5
$T/venv/bin/pull_files.py --target JetMET 2>&1 | grep -E '2024_Summer24|ERROR' | head -8
time $T/venv/bin/python probe_hgg_original.py '$URL' GluGluHto2G_M-125_amcatnlo_2024 0 20000 $T/out
"
find "$T" -maxdepth 1; du -sh "$T"
cd / && rm -rf "$T"; ls -d "$T" 2>&1
