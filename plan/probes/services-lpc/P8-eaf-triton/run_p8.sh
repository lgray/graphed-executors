# P8: EAF Triton (triton.fnal.gov:443, gRPC+TLS) from an LPC batch worker. Upload p8.tgz to ~/graphed-probe-p8 first.
set -u
D=$HOME/graphed-probe-p8; cd $D && tar xzf p8.tgz
echo "### $(date -u +%FT%TZ) submit host $(hostname -f)"
out=$(python3 submit_job.py t.sub); echo "$out"
export SCHEDD=$(sed -E 's/.*schedd=([^ ]+).*/\1/' <<<"$out"); C=$(sed -E 's/.*cluster=([0-9]+).*/\1/' <<<"$out")
python3 watch.py $C 1500 1 | tail -6
echo "--- t.out"; cat t.out 2>/dev/null; echo "--- t.err"; head -20 t.err 2>/dev/null
echo "### cleanup"; python3 -c "
import htcondor2 as h, sched; n, s = sched.choose(); print(s.act(h.JobAction.Remove, 'ClusterId == $C'))" 2>&1 | tail -1
sleep 5; python3 -c "
import sched; n, s = sched.choose(); print('left:', len(s.query(constraint='ClusterId == $C', projection=['ClusterId'])))"
cd $HOME && rm -rf $D; ls -d $D 2>&1
