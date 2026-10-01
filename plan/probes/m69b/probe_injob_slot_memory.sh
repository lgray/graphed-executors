#!/bin/sh
# What a driver job can read as its slot's memory: Memory in $_CONDOR_MACHINE_AD for a 3000 MiB request.
#   docker run -d --rm --name m69b-injob-probe m68b-minicondor:local; docker exec m69b-injob-probe sh /p/...  (see the Bash call)
cd /tmp && cat > slotmem.sub <<'SUB'
executable = /bin/sh
arguments = "-c 'grep -E ""^(Memory|TotalSlotMemory|SlotType|Cpus) ="" $_CONDOR_MACHINE_AD; grep -E ""^RequestMemory ="" $_CONDOR_JOB_AD'"
request_memory = 3000
output = slotmem.out
error = slotmem.err
log = slotmem.log
queue
SUB
condor_submit slotmem.sub >/dev/null && condor_wait -wait 120 slotmem.log >/dev/null; cat slotmem.out slotmem.err
