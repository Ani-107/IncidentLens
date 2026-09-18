import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "incidentlens_eval_lib", Path.cwd() / "tests" / "eval" / "incidentlens_eval_lib.py"
)
_lib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lib)


def evaluate(instance):
    return _lib.evaluate_metric(instance, "summary_quality")
