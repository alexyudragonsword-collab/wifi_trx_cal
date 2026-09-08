"""Pilot tone placement and insertion, per numerology.

Two pilot tables, keyed by the OFDM numerology of the config:

* **802.11ax/be** (78.125 kHz spacing): the RU pilot sets of 802.11ax
  Table 27-21 — 242-tone RU 8 pilots (±22, ±48, ±90, ±116), 484-tone 16,
  996-tone 16; the 160 MHz (2×996) set is the 80 MHz set placed at ±512
  and the 320 MHz (4×996, 802.11be) set is the 160 MHz set placed at
  ±1024, exactly as the tone plans duplicate.  32 and 64 pilots.
* **legacy 802.11a/n/ac** (312.5 kHz spacing): 20 MHz 4 (±7, ±21),
  40 MHz 6 (±11, ±25, ±53), 80 MHz 8 (±11, ±39, ±75, ±103), 160 MHz 16
  (the 80 MHz set at ±128).

Until 0.7.17 the legacy table was the only one and was applied to the
11ax/be numerology as well — 6 pilots at 40 MHz where the standard has
16, and a 320 MHz set reaching only ±487 of ±1992 — so every
pilot-tracked reading (config 4 of ``pn_cpe_study``, the standards
comparison, ``cal.tracking``) under-counted the 11ax/be pilots.

The model's active block is contiguous and symmetric about DC
(``OFDMConfig.active_tone_indices``): it has no DC gap and no
inter-segment null tones.  The standard's pilot indices are therefore
mapped **by rank** — a pilot at signed index ``p`` sits at the same
ordinal position among the model's active tones as it does among the
standard's — which keeps the pilot count and the lever arm across the
band while shifting each pilot by at most the number of null tones
inside it (2–44 tones).  Data OFDM from the vendored generator fills all
active tones; ``insert_pilots`` overwrites the pilot positions with a
known BPSK sequence so preamble-less tracking (residual CFO/SCO, common
phase error) is possible.
"""
from __future__ import annotations

import numpy as np

from .ofdm import SUBCARRIER_SPACING_HZ, OFDMConfig, OFDMWaveform, generate_ofdm

LEGACY_SUBCARRIER_SPACING_HZ = 312.5e3


def _duplicate(half: tuple[int, ...], offset: int) -> tuple[int, ...]:
    """The positive half of a set built by placing ``half`` at ±offset."""
    return tuple(sorted([offset - p for p in half] + [offset + p for p in half]))


# positive-half pilot indices; the negative half mirrors them
_HE_PILOTS = {
    20e6: (22, 48, 90, 116),
    40e6: (10, 36, 78, 104, 130, 156, 198, 224),
    80e6: (24, 92, 158, 226, 266, 334, 400, 468),
}
_HE_PILOTS[160e6] = _duplicate(_HE_PILOTS[80e6], 512)
_HE_PILOTS[320e6] = _duplicate(_HE_PILOTS[160e6], 1024)

_LEGACY_PILOTS = {
    20e6: (7, 21),
    40e6: (11, 25, 53),
    80e6: (11, 39, 75, 103),
}
_LEGACY_PILOTS[160e6] = _duplicate(_LEGACY_PILOTS[80e6], 128)

# positive-half occupied ranges (inclusive) of the standard tone plans —
# the null-tone structure the model's contiguous block omits
_HE_RANGES = {
    20e6: ((2, 122),),
    40e6: ((3, 244),),
    80e6: ((3, 500),),
    160e6: ((12, 509), (515, 1012)),
    320e6: ((12, 509), (515, 1012), (1036, 1533), (1539, 2036)),
}
_LEGACY_RANGES = {
    20e6: ((1, 26),),
    40e6: ((2, 58),),
    80e6: ((2, 122),),
    160e6: ((6, 126), (130, 250)),
}


def _tables(config: OFDMConfig):
    if config.subcarrier_spacing_hz == SUBCARRIER_SPACING_HZ:
        return "802.11ax/be", _HE_PILOTS, _HE_RANGES
    if config.subcarrier_spacing_hz == LEGACY_SUBCARRIER_SPACING_HZ:
        return "legacy 802.11a/n/ac", _LEGACY_PILOTS, _LEGACY_RANGES
    raise ValueError(
        f"no pilot table for a {config.subcarrier_spacing_hz / 1e3:g} kHz "
        "subcarrier spacing (78.125 kHz = 11ax/be, 312.5 kHz = legacy)")


def _pilot_half(config: OFDMConfig):
    """(positive-half pilot indices, positive-half occupied ranges) of the
    standard for this numerology and bandwidth, or a ValueError naming
    what is defined — never a guess."""
    name, pilots, ranges = _tables(config)
    half = pilots.get(config.bandwidth_hz)
    if half is None:
        raise ValueError(
            f"no {name} pilot set for {config.bandwidth_hz / 1e6:g} MHz; "
            f"defined: {', '.join(f'{b / 1e6:g}' for b in sorted(pilots))} MHz")
    return half, ranges[config.bandwidth_hz]


def standard_pilot_tones(config: OFDMConfig) -> np.ndarray:
    """Signed pilot tone indices of the standard for this numerology and
    bandwidth (before the rank mapping onto the model's block)."""
    half, _ = _pilot_half(config)
    return np.array([-p for p in reversed(half)] + list(half), dtype=int)


def pilot_positions(config: OFDMConfig) -> np.ndarray:
    """Column indices (into the n_active axis) of the pilot tones.

    Rank-mapped: the k-th occupied tone of the standard's plan is the
    k-th active tone of the model, so the pilot count and the spread
    across the band are the standard's even though the model has no
    null-tone gaps.
    """
    half, ranges = _pilot_half(config)
    occupied = np.concatenate([np.arange(lo, hi + 1) for lo, hi in ranges])
    n_half = config.n_active // 2
    if occupied.size != n_half:
        raise ValueError(
            f"tone plan mismatch: standard occupies {occupied.size} tones per "
            f"side, model {n_half}")
    ranks = np.searchsorted(occupied, np.asarray(half))
    assert np.all(occupied[ranks] == half), "pilot not on an occupied tone"
    # model positive tones 1..n_half are at columns n_half..2 n_half-1;
    # negative tones -n_half..-1 at columns 0..n_half-1
    pos_cols = n_half + ranks
    neg_cols = n_half - 1 - ranks
    return np.sort(np.concatenate([neg_cols, pos_cols])).astype(int)


def pilot_sequence(n_symbols: int, n_pilots: int, seed: int = 42) -> np.ndarray:
    """Known BPSK pilot values, (n_symbols, n_pilots)."""
    rng = np.random.default_rng(seed)
    return (2.0 * rng.integers(0, 2, size=(n_symbols, n_pilots)) - 1.0).astype(complex)


def generate_ofdm_with_pilots(config: OFDMConfig,
                              pilot_seed: int = 42) -> tuple[OFDMWaveform, np.ndarray]:
    """Data OFDM with pilot positions overwritten by known BPSK.

    Returns (waveform, pilot_cols).
    """
    base = generate_ofdm(config)
    cols = pilot_positions(config)
    symbols = base.tx_symbols.copy()
    symbols[:, cols] = pilot_sequence(config.n_symbols, cols.size, pilot_seed)
    wf = generate_ofdm(config, symbols=symbols)
    return wf, cols
