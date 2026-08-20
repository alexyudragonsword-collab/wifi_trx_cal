# Vendored from PA_DPD:src/padpd/metrics/evm.py (internal sibling repo), adapted for wifitrx.
# Upstream changes should be ported manually; see PROVENANCE.md.
"""Error Vector Magnitude.

EVM is computed between received and reference constellation points after
equalization:

- ``equalize="scalar"``: one complex gain for the whole burst (least
  squares). Keeps frequency-dependent (memory) distortion visible in EVM.
- ``equalize="per_tone"``: independent complex gain per subcarrier, like a
  standard receiver with per-tone channel estimation. Hides linear
  filtering, exposes only nonlinear distortion.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..waveform.ofdm import OFDMWaveform, demodulate_ofdm


@dataclass
class EVMResult:
    db: float
    percent: float

    def __str__(self) -> str:
        return f"{self.db:.2f} dB ({self.percent:.3f} %)"


def _evm_from_error(err: np.ndarray, ref: np.ndarray,
                    dof_scale: float = 1.0) -> EVMResult:
    ratio = np.sqrt(dof_scale * (np.abs(err) ** 2).mean()
                    / (np.abs(ref) ** 2).mean())
    return EVMResult(db=float(20 * np.log10(ratio)), percent=float(100 * ratio))


def evm(rx: np.ndarray, tx: np.ndarray, equalize: str = "scalar") -> EVMResult:
    """EVM between received and transmitted constellation points.

    ``rx``/``tx`` are (n_symbols, n_tones) or flat arrays of complex points.

    The equalizer gains are least-squares fitted to the very points being
    scored, so the fit absorbs the noise component aligned with each fitted
    parameter: 1/N of the noise power per complex gain fitted over N
    points.  The residual is rescaled by N/(N-k) (Bessel-type
    degrees-of-freedom correction) so the reported EVM is unbiased.
    Without it a 6-symbol per-tone reading under-reports noise by 0.79 dB
    while a 24-symbol reading under-reports by 0.18 dB — a numerology-
    dependent instrument bias that once cancelled the genuine 0.66 dB
    occupied-bandwidth difference between 11n and 11ax at 20 MHz.
    """
    rx = np.asarray(rx)
    tx = np.asarray(tx)
    if equalize == "scalar":
        g = np.vdot(tx, rx) / np.vdot(tx, tx)
        err = rx / g - tx
        dof = rx.size / (rx.size - 1)
    elif equalize == "per_tone":
        if rx.ndim != 2:
            raise ValueError("per_tone equalization needs (n_symbols, n_tones)")
        n_sym = rx.shape[0]
        if n_sym < 2:
            raise ValueError(
                "per_tone equalization needs >= 2 symbols: with one symbol "
                "the per-tone fit absorbs the entire error and the EVM "
                "reading is vacuous")
        g = (np.conj(tx) * rx).sum(axis=0) / (np.abs(tx) ** 2).sum(axis=0)
        err = rx / g - tx
        dof = n_sym / (n_sym - 1)
    else:
        raise ValueError(f"unknown equalize mode: {equalize}")
    return _evm_from_error(err, tx, dof_scale=dof)


def evm_of_signal(y: np.ndarray, ref: OFDMWaveform,
                  equalize: str = "scalar") -> EVMResult:
    """Demodulate a time-domain signal against ``ref`` and compute EVM."""
    rx = demodulate_ofdm(y, ref)
    return evm(rx, ref.tx_symbols, equalize=equalize)
