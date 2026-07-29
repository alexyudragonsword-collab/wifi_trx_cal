"""Bit-true test vectors for RTL verification of the correction datapaths.

The digital team's RTL (widely-linear w2 FIR, GMP DPD engine) is verified
by replaying these vectors: quantized stimulus in, expected quantized
response out, computed by the same bit-true arithmetic model the
coefficients were signed off with (deploy/fixed_point.py).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..chain.tx import apply_widely_linear
from .fixed_point import FixedPointPolyModel, quantize_symmetric


def make_wl_vectors(w2: np.ndarray, n_samples: int = 4096,
                    coeff_bits: int = 12, sig_bits: int = 14,
                    seed: int = 0) -> dict:
    """Widely-linear corrector vectors: y = x + w2_q * conj(x_q)."""
    rng = np.random.default_rng(seed)
    x = 0.25 * (rng.standard_normal(n_samples)
                + 1j * rng.standard_normal(n_samples))
    x_q = quantize_symmetric(x, sig_bits)
    w2_q = quantize_symmetric(np.asarray(w2, dtype=complex), coeff_bits)
    y = apply_widely_linear(x_q, None, w2_q)
    return {"x": x_q, "y_expected": y, "w2_q": w2_q,
            "coeff_bits": coeff_bits, "sig_bits": sig_bits, "seed": seed,
            "kind": "widely_linear"}


def make_dpd_vectors(dpd_model, n_samples: int = 4096,
                     coeff_bits: int = 16, sig_bits: int = 16,
                     seed: int = 1) -> dict:
    """GMP DPD engine vectors via the bit-true fixed-point evaluator."""
    rng = np.random.default_rng(seed)
    x = 0.2 * (rng.standard_normal(n_samples)
               + 1j * rng.standard_normal(n_samples))
    fp = FixedPointPolyModel(dpd_model, w_bits=coeff_bits, sig_bits=sig_bits)
    y = fp(x)
    return {"x": x, "y_expected": y,
            "coeffs_q": quantize_symmetric(dpd_model.coeffs, coeff_bits),
            "coeff_bits": coeff_bits, "sig_bits": sig_bits, "seed": seed,
            "kind": "gmp_dpd"}


def save_vectors(vec: dict, path: str | Path) -> Path:
    p = Path(path)
    np.savez_compressed(p, **vec)
    csv = p.with_suffix(".csv")
    x, y = vec["x"], vec["y_expected"]
    rows = ["index,x_re,x_im,y_re,y_im"]
    rows += [f"{i},{a.real:.12e},{a.imag:.12e},{b.real:.12e},{b.imag:.12e}"
             for i, (a, b) in enumerate(zip(x, y))]
    csv.write_text("\n".join(rows))
    return p if p.suffix == ".npz" else p.with_suffix(p.suffix + ".npz")


def verify_vectors(path: str | Path, dpd_model=None) -> bool:
    """Replay the stimulus through the bit-true model; must reproduce
    y_expected exactly."""
    with np.load(path, allow_pickle=False) as d:
        kind = str(d["kind"])
        x, y_exp = d["x"], d["y_expected"]
        if kind == "widely_linear":
            y = apply_widely_linear(x, None, d["w2_q"])
        elif kind == "gmp_dpd":
            if dpd_model is None:
                raise ValueError("gmp_dpd vectors need the dpd_model")
            fp = FixedPointPolyModel(dpd_model, w_bits=int(d["coeff_bits"]),
                                     sig_bits=int(d["sig_bits"]))
            y = fp(x)
        else:
            raise ValueError(f"unknown vector kind {kind!r}")
    return bool(np.allclose(y, y_exp, rtol=0, atol=1e-15))
