# continue probe_r16_dag_removed_driver.py: the driver node held (ON_EXIT_OR_EVICT output transfer of a
# missing result.pkl); remove each held driver node, as a user or a site's held-job removal policy would
for i in 1 2 3 4; do
  for t in $(seq 1 60); do
    id=$(condor_q -af:j 'DAGNodeName' 'JobStatus' -constraint 'DAGNodeName == "driver" && JobStatus == 5' | awk '{print $1}' | head -1)
    [ -n "$id" ] && break; sleep 3
  done
  [ -z "$id" ] && { echo "no held driver on round $i"; break; }
  echo "round $i: removing held driver node $id"; condor_rm $id >/dev/null
done
for t in $(seq 1 40); do condor_q -af ClusterId | grep -q . || break; sleep 3; done
echo "queue after:"; condor_q -af ClusterId DAGNodeName JobStatus
condor_history -af ClusterId DAGNodeName JobStatus ExitCode RemoveReason -limit 10
python3 -c "import pickle;print('result.pkl:', pickle.load(open('/home/submituser/r16b2-removed/result.pkl','rb')))"
grep -E "EXITING|failed|Retry|RETRY" /home/submituser/r16b2-removed/run.dag.dagman.out | tail -8
