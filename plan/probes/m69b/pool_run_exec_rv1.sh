#!/bin/bash
# root inside the set-up container: CI test-htcondor's pytest line + scoped coverage, as submituser, into /out/<stem>.*
STEM=$1; shift
mkdir -p /out && chown submituser:submituser /out
su submituser -s /bin/bash -c "cd /work && export PATH=/opt/venv/bin:\$PATH COVERAGE_PROCESS_START=/work/.coveragerc-htcondor COVERAGE_RCFILE=/work/.coveragerc-htcondor COVERAGE_FILE=/work/.coverage && rm -f /work/.coverage /work/.coverage.* && \
 python -m pytest -p no:cacheprovider -rfEs -o faulthandler_timeout=300 $* --cov --cov-config=.coveragerc-htcondor --cov-branch --cov-fail-under=0 > /out/$STEM.txt 2>&1; echo pytest-exit=\$? >> /out/$STEM.txt; \
 mv .coverage .coverage.driver; coverage combine >> /out/$STEM.cov 2>&1; coverage report --show-missing >> /out/$STEM.cov 2>&1; \
 coverage json --rcfile=.coveragerc-htcondor -o /out/$STEM.json >/dev/null 2>&1; python scripts/coverage_gate.py /out/$STEM.json 90 >> /out/$STEM.cov 2>&1; echo gate-exit=\$? >> /out/$STEM.cov; \
 coverage xml --rcfile=.coveragerc-htcondor -o /out/$STEM.xml >/dev/null 2>&1"
echo "queue after: $(condor_q -allusers -totals 2>/dev/null | grep 'Total for all users')" >> /out/$STEM.txt
