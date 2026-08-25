import ast

import numpy as np

from .base import PAModel, nmse_db
from .saleh import SalehPA
from .memory_polynomial import MemoryPolynomialModel
from .gmp import GMPModel
from .reference_pa import ReferencePA
from .drift import DriftingReferencePA
from .hb_import import WienerHammersteinPA, load_amam_table, load_hb_pa, s21_to_fir
from .scaled import DriftingScaledPA, ScaledPA

_MODEL_CLASSES = {cls.__name__: cls
                  for cls in (SalehPA, MemoryPolynomialModel, GMPModel,
                              WienerHammersteinPA)}


def load_model(path: str) -> PAModel:
    """Load a model saved with :meth:`PAModel.save`."""
    d = np.load(path, allow_pickle=False)
    class_name = str(d["class_name"])
    if class_name not in _MODEL_CLASSES:
        raise ValueError(f"unknown model class in {path}: {class_name}")
    model = _MODEL_CLASSES[class_name](**ast.literal_eval(str(d["config"])))
    if "coeffs" in d:
        model.coeffs = d["coeffs"]
    return model


__all__ = [
    "PAModel", "load_model", "nmse_db",
    "SalehPA", "MemoryPolynomialModel", "GMPModel", "ReferencePA",
    "DriftingReferencePA", "WienerHammersteinPA",
    "load_amam_table", "load_hb_pa", "s21_to_fir",
    "ScaledPA", "DriftingScaledPA",
]
