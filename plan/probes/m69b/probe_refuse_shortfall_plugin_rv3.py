"""pytest plugin for run_refuse_shortfall_rv3.sh: `_refuse_shortfall` made a no-op, nothing else changed."""
import graphed_histogram.boost as boost

boost._refuse_shortfall = lambda *args, **kwargs: None
