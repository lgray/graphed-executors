Example: an H→γγ analysis, translated
=====================================

``examples/hgg/analysis.py`` is a coffea processor rewritten for graphed: ``inclusive_processor.py``,
a standalone distillation of HiggsDNA's H→γγ inclusive base processor. It covers the lumi mask, MET
filters and triggers, photon preselection, diphoton building, the detector-level fiducial cut, the
cleaned jet variables, and the particle-level truth and fiducial flags. For each chunk it writes one
flat parquet file of diphoton candidates and counts the chunk's events and weights. One plan runs
it over a whole fileset, MC and data together, and returns each dataset's summed counters.

The translation keeps the original's methods, names and cut values. Events are coffea NanoEvents in
graphed mode:

.. code-block:: python

   events = NanoEventsFactory.from_root(
       files,  # {file: {"object_path": "Events", "steps": [[start, stop], ...]}}
       schemaclass=NanoAODSchema,
       mode="graphed",
       metadata={"dataset": dataset},
   ).events()

The analysis reads the same files the original reads: HiggsDNA's ``infer_nano_version``, plus the
metaconditions, golden JSON and jet-ID JSONs, found through ``importlib.resources`` inside the
installed ``higgs_dna``. ``plan(fileset, year=..., out=...)`` takes coffea's
``{dataset: {file: {"object_path": "Events", "steps": [[start, stop], ...]}}}`` and builds one task
per step of every file. Any runner in this package runs it.

Data and MC take different branches in Python while the processor records (the lumi mask, the
weights, the truth columns), so each dataset records its own graph. ``dataset_plan`` makes one
``graphed.aggregate_plan`` per dataset: its outputs are the counters, and its one write is
``graphed.awkward.parquet_write`` of the flat record, whose part metadata holds that chunk's own
weight sums. ``graphed.collate`` joins the datasets' plans into the one plan ``plan`` returns. Each
task reads its chunk once, writes its part, and returns its counters, and the runner tree-reduces
the counters with ``coffea.processor.accumulate``, as coffea's ``Runner`` does. The value is
``{dataset: counters}``. ``plan({dataset: files})`` runs one dataset on its own, so datasets can
be submitted separately, and a dict union of their values is the same result.


Running it
----------

The example lives in this repository's ``examples/hgg``, not in the installed package, so run it from
a clone, and install the clone. It also needs coffea with graphed mode, which lives in a fork until it
is released, the ``uproot`` commit that fork needs, and HiggsDNA installed without its dependencies
(they pull in torch, xgboost and onnx, which this processor does not use):

.. code-block:: bash

   git clone https://github.com/graphed-org/graphed-executors
   cd graphed-executors
   pip install . vector correctionlib pyarrow \
     "coffea @ git+https://github.com/graphed-org/coffea-graphed-mvp@b2612ab03932ba61f183eb5f582870109020446b" \
     "uproot @ git+https://github.com/scikit-hep/uproot5@ca3a8a28c0846ea4c6f42452f69e3cce2939bf62"
   pip install --no-deps \
     "higgs-dna @ git+https://gitlab.cern.ch/cms-analysis/general/HiggsDNA.git@d17930519cafd8eec06e74e4e9fb7add3cf62b5a"

The processor reads the 2024 golden JSON and jet-ID set from inside the installed ``higgs_dna``, where
HiggsDNA's own ``pull_files.py`` puts them. Its ``--target GoldenJSON`` downloads the golden JSONs.
Its ``--target JetMET`` copies the jet corrections from ``/cvmfs``, which a laptop does not have, so
copy the jet-ID set kept beside the example instead (the same bytes as
``/cvmfs/cms-griddata.cern.ch/cat/metadata/JME/Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/2026-06-05/jetid.json.gz``):

.. code-block:: bash

   python -m higgs_dna.scripts.pull_files --target GoldenJSON
   python -c "import higgs_dna, pathlib, shutil; d = pathlib.Path(higgs_dna.__file__).parent / 'systematics/JSONs/POG/JME/2024_Summer24'; d.mkdir(parents=True, exist_ok=True); shutil.copy('examples/hgg/jetid.json.gz', d)"

``examples/hgg/run_local.py`` runs one dataset's files on this machine and prints the counters.
``examples/hgg/nano.root`` is the first 200 events of a 2024 GluGluH→γγ NanoAODv15 file
(``/store/mc/RunIII2024Summer24NanoAODv15/GluGluH-Hto2G_Par-M-125_TuneCP5_13p6TeV_amcatnloFXFX-pythia8/NANOAODSIM/150X_mcRun3_2024_realistic_v2-v2/120000/acebfb52-a25b-48bc-b9f6-80fe54a98d56.root``).
Split in two, on two threads:

.. code-block:: bash

   python examples/hgg/run_local.py examples/hgg/nano.root --dataset MC --year 2024 --parts 2 --workers 2 --out out

It warns three times (numpy's ``RuntimeWarning``: overflow in ``sinh``, overflow in ``cosh``, invalid
value in ``subtract``), then prints the counters:

::

   {
    "MC": {
     "nTot": 200,
     "nPos": 170,
     "nNeg": 30,
     "nEff": 140,
     "genWeightSum": 29368.841796875
    }
   }

and writes ``out/MC/nominal/nano_Events_0-100.parquet`` and ``nano_Events_100-200.parquet``. The same
plan runs on HTCondor pilots, here started on your laptop as in :doc:`htcondor`, from
``examples/hgg``, which holds ``analysis.py`` and the file:

.. code-block:: python

   import analysis
   from graphed_executors.htcondor_backend import HTCondorBackend, HTCondorRunner, LocalPilots

   fileset = {"MC": {"nano.root": {"object_path": "Events", "steps": [[0, 100], [100, 200]]}}}
   plan = analysis.plan(fileset, year="2024", out="out")

   backend = HTCondorBackend(LocalPilots(), n_pilots=2, host="127.0.0.1")
   with HTCondorRunner(backend) as runner:
       print(runner.run(plan).value)

::

   pilot myhost:88812:fdd5afac serving http://127.0.0.1:10000
   pilot myhost:88813:1d8a2a56 serving http://127.0.0.1:10000
   {'MC': {'nTot': 200, 'nPos': 170, 'nNeg': 30, 'nEff': 140, 'genWeightSum': 29368.841796875}}

The counters are the ones the thread run printed, and the same two parts are written. On a pool,
``analysis.py`` goes in ``user_modules`` and the packages above in the environment the pilots get;
the file names become ``root://`` URLs the execute nodes can open.


What changed, and why
---------------------

Nothing is read when the processor runs, so wherever the original needs a value on the spot, the
translation has to spell that step another way. These are all eleven such places:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Original
     - Translation
   * - ``int(ak.num(...))``, ``len(events)``
     - The counters (``nTot``, ``nPos``, ``nNeg``, ``genWeightSum``, and the two weight sums in the
       metadata) are plan outputs, computed per chunk. ``Counters`` converts each counter to the
       original's Python type (``int`` or ``float``); the part's metadata is the ``str`` of each
       float32 sum.
   * - ``.to_numpy()``
     - The same counters. The old-NanoAOD supercluster-η projection uses the deferred PV columns
       directly.
   * - ``array["field"] = value``
     - ``gak.with_field(array, value, "field")``.
   * - ``ak.Array({...})`` for the flat output record
     - ``gak.zip`` of the flat columns.
   * - ``ak.to_arrow_table`` and ``pq.write_table`` inside ``process``
     - A ``parquet_write`` beside the counters, in the same pass: ``extensionarray=False``, the
       record's fields zipped in sorted order, and the part's key-value metadata replacing the
       schema's (the original's ``pa.table`` rebuild drops the schema's own).
   * - ``events.attrs["@events_factory"]._partition_key`` for the part name
     - ``part_name`` builds the name from the task's partition:
       ``<file stem>_Events_<start>-<stop>.parquet``. The original has the file's UUID where this
       has the file's stem. A file without explicit ``steps`` is refused, since a blind partition
       has no range to name its part by (and the counters depend on the chunking).
   * - ``LumiMask(path)(events.run, events.luminosityBlock)``
     - ``lumi_mask(run, lumi, year)``, an External recorded through
       ``graphed.preserve.externals.record_external``. Its payload is the golden JSON's bytes and
       its content hash is their SHA-256. Its evaluator is coffea's ``LumiMask`` on each chunk's
       run and lumi values. The plan therefore carries the certification it applied.
   * - ``correctionlib.CorrectionSet.evaluate`` for the jet ID
     - ``gak.apply_correction`` with a call template. The JSON is gunzipped first, because the
       correctionlib External parses JSON bytes.
   * - ``numpy.where``, ``numpy.copy``
     - ``gak.where``. The copy is dropped, since deferred arrays are never modified in place.
   * - ``if ak.num(diphotons.pt, axis=0) > 0:`` guards around jet cleaning
     - Deleted. The cleaning ops are defined on an empty chunk and give the same empty masks.
   * - ``ak.with_name(..., "PtEtaPhiMCandidate")``, which needs ``charge``
     - Unchanged. The records are zipped with ``charge`` already, and graphed NanoEvents carry
       coffea's candidate behaviors into each task.



How the translation is checked
------------------------------

The repository's tests use the original script as the reference. They import the file, kept
byte-identical and identified by its SHA-256, and call its ``process()`` on NanoEvents built the way
the script's ``__main__`` builds them, one chunk per range. They then compare each part the
translation writes against the original's part for the same range. ``compare_part`` covers:

* the counters, by ``==`` and by each value's Python type;
* the arrow schema: names, order, types and nullability;
* each column's validity bitmap;
* each column's valid values, bit for bit, with floats compared through their same-width
  unsigned view so NaN positions count;
* the key-value metadata.

The inputs are two 200-event NanoAOD v15 files, one MC and one data, each built by a script
checked in beside it. The MC file is the first 200 events of a 2024 GluGluH→γγ NanoAODv15 file.
The data file has certified and uncertified lumi sections, and its builder puts the diphoton
signal only in events 0–59, so its (100, 200) chunk selects nothing: that part has zero rows and
the original's schema. One plan over both runs on ``SequentialRunner`` and on
``SubmitRunner(ThreadBackend(2))``: its value must equal ``coffea.processor.accumulate`` of the
original's counters, and each part must match the original's part for its range. The tests also
record every events object coffea hands out while the plan is built and run, and require each to be
graphed NanoEvents.

``examples/hgg/validate_real.py --parts 2`` runs the same comparison on real 2024 NanoAOD over
xrootd: the first file of ``GluGluHto2G_M-125_amcatnlo_2024`` and the first of ``DataC_2024``. It
prints each file's entry count, every part's ``compare_part`` result, and each dataset's
accumulated counters beside the plan's. It exits 1 on any difference.
