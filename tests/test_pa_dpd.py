"""M0 smoke tests: vendored PA models and DPD."""
import numpy as np

from wifitrx.pa import SalehPA, MemoryPolynomialModel, GMPModel, ReferencePA, nmse_db
from wifitrx.dpd import ILAPredistorter


def _test_signal(n=4096, seed=0):
    rng = np.random.default_rng(seed)
    x = (rng.standard_normal(n) + 1j * rng.standard_normal(n)) / np.sqrt(2.0)
    return x * 0.15


def test_saleh_compresses():
    pa = SalehPA()
    r = np.linspace(0.01, 1.0, 100)
    gain = np.abs(pa(r.astype(complex))) / r
    assert gain[-1] < gain[0]  # compression at high drive


def test_mp_fits_reference_pa():
    x = _test_signal()
    pa = ReferencePA(drive=0.14)
    y = pa(x)
    model = MemoryPolynomialModel(order=7, memory_depth=4).fit(x, y)
    assert nmse_db(y, model(x)) < -35.0


def test_ila_linearizes():
    x = _test_signal(8192)
    pa = ReferencePA(drive=0.14)
    dpd = ILAPredistorter(model_factory=GMPModel, n_iterations=2).fit(pa, x)
    y_lin = pa(dpd(x))
    g = np.vdot(x, y_lin) / np.vdot(x, x)
    nmse_post = nmse_db(g * x, y_lin)
    y_raw = pa(x)
    g0 = np.vdot(x, y_raw) / np.vdot(x, x)
    nmse_pre = nmse_db(g0 * x, y_raw)
    assert nmse_post < nmse_pre - 10.0
