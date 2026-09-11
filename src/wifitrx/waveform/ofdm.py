# Vendored from PA_DPD:src/padpd/waveform/ofdm.py (internal sibling repo), adapted for wifitrx.
# Upstream changes should be ported manually; see PROVENANCE.md.
"""802.11be-style OFDM waveform generation and demodulation.

Scope: waveform-level model for PA/DPD work. All active tones carry known
random QAM data (no preamble, pilots, or channel coding). Numerology follows
802.11ax/be: 78.125 kHz subcarrier spacing, 12.8 us symbol, 0.8 us guard
interval by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .qam import qam_modulate
from ..units import papr_db  # noqa: F401 — re-export

SUBCARRIER_SPACING_HZ = 78.125e3

# Active (data + pilot) tone counts per channel bandwidth, 802.11ax/be-like.
_ACTIVE_TONES = {
    20e6: 242,
    40e6: 484,
    80e6: 996,
    160e6: 1992,
    320e6: 3984,
}

# Legacy 802.11a/n/ac numerology (312.5 kHz spacing): data + pilots per
# bandwidth — 52 of 64 tones at 20 MHz, 114 of 128 at 40 MHz (11n),
# 242 of 256 / 484 of 512 for 11ac 80/160 MHz.
_ACTIVE_TONES_LEGACY = {
    20e6: 52,
    40e6: 114,
    80e6: 242,
    160e6: 484,
}


@dataclass
class OFDMConfig:
    bandwidth_hz: float = 160e6
    qam_order: int = 1024
    n_symbols: int = 20
    oversampling: int = 4
    cp_fraction: float = 1 / 16  # 0.8 us GI over 12.8 us symbol
    window_fraction: float = 1 / 32  # raised-cosine edge, 0.4 us default
    # 78.125 kHz = 802.11ax/be numerology (12.8 us symbol); legacy
    # 802.11a/n/ac uses 312.5 kHz (3.2 us symbol, cp_fraction 1/4 for the
    # 0.8 us long GI, 1/8 for the 0.4 us short GI)
    subcarrier_spacing_hz: float = SUBCARRIER_SPACING_HZ
    seed: int | None = 0
    #: which subcarriers carry something.  None (the default) is the
    #: historical contiguous block symmetric about DC, bit for bit.
    #: "standard" builds the numerology's real plan, with the DC gap and
    #: the inter-segment nulls as actual holes; a TonePlan instance is
    #: taken as given (see waveform.tone_plan, e.g. for puncturing).
    tone_plan: object | None = None
    #: which pilot tones the frame carries.  "standard" (the default)
    #: uses the numerology's own pilot set and REFUSES a plan that does
    #: not contain it — a punctured or sub-band plan has a different
    #: pilot set in the standard, and guessing it would be inventing a
    #: specification.  "model" opts in to an evenly-spaced set of the
    #: same size, which is this model's own and is labelled as such
    #: wherever it is reported.
    pilot_set: str = "standard"

    @property
    def fft_size(self) -> int:
        n = self.bandwidth_hz / self.subcarrier_spacing_hz
        if abs(n - round(n)) > 1e-9:
            raise ValueError(
                "bandwidth must be a multiple of the subcarrier spacing")
        return int(round(n))

    def plan(self):
        """The resolved TonePlan.  Built fresh each call, so ``replace``
        on the config cannot leave a stale plan behind."""
        from .tone_plan import TonePlan, contiguous, standard
        if self.tone_plan is None:
            return contiguous(self._block_n_active())
        if isinstance(self.tone_plan, TonePlan):
            return self.tone_plan
        if self.tone_plan == "standard":
            return standard(self.bandwidth_hz, self.subcarrier_spacing_hz,
                            SUBCARRIER_SPACING_HZ)
        raise ValueError(f"unknown tone_plan {self.tone_plan!r}; use None, "
                         '"standard", or a TonePlan')

    @property
    def n_active(self) -> int:
        if self.tone_plan is not None:
            return self.plan().n_active
        return self._block_n_active()

    def _block_n_active(self) -> int:
        # per-numerology occupancy tables; a fraction-of-FFT heuristic
        # covers non-standard bandwidths (0.47 per side ~ 11ax edge,
        # 0.41 ~ the legacy 52-of-64 ratio)
        if (self.subcarrier_spacing_hz == SUBCARRIER_SPACING_HZ
                and self.bandwidth_hz in _ACTIVE_TONES):
            return _ACTIVE_TONES[self.bandwidth_hz]
        if (self.subcarrier_spacing_hz == 312.5e3
                and self.bandwidth_hz in _ACTIVE_TONES_LEGACY):
            return _ACTIVE_TONES_LEGACY[self.bandwidth_hz]
        frac = 0.47 if self.subcarrier_spacing_hz == SUBCARRIER_SPACING_HZ \
            else 0.41
        return 2 * int(frac * self.fft_size)

    @property
    def cp_len(self) -> int:
        return int(round(self.fft_size * self.cp_fraction))

    @property
    def window_len(self) -> int:
        w = int(round(self.fft_size * self.window_fraction))
        if w > self.cp_len:
            raise ValueError("window transition must fit inside the CP")
        return w

    @property
    def sample_rate_hz(self) -> float:
        return self.bandwidth_hz * self.oversampling

    def active_tone_indices(self) -> np.ndarray:
        """Signed tone indices of the resolved plan.  With ``tone_plan``
        unset this is the historical contiguous block, symmetric around
        (and excluding) DC."""
        return self.plan().indices


@dataclass
class OFDMWaveform:
    """Generated waveform plus everything needed to demodulate it."""

    x: np.ndarray  # complex baseband samples, unit average power
    tx_symbols: np.ndarray  # (n_symbols, n_active) constellation points
    config: OFDMConfig
    scale: float  # divide-by factor applied for unit-power normalization
    tone_indices: np.ndarray = field(repr=False, default=None)

    @property
    def sample_rate_hz(self) -> float:
        return self.config.sample_rate_hz


def generate_ofdm(config: OFDMConfig,
                  symbols: np.ndarray | None = None) -> OFDMWaveform:
    """Generate an oversampled OFDM burst with known random QAM payload.

    wifitrx adaptation: ``symbols`` optionally provides the (n_symbols,
    n_active) constellation points directly (used for preamble/pilot
    frames); default behavior is unchanged.
    """
    rng = np.random.default_rng(config.seed)
    nfft = config.fft_size
    os_nfft = nfft * config.oversampling
    cp = config.cp_len * config.oversampling
    tones = config.active_tone_indices()

    if symbols is not None:
        tx_symbols = np.asarray(symbols, dtype=complex)
        if tx_symbols.shape != (config.n_symbols, tones.size):
            raise ValueError(
                f"symbols must be (n_symbols, {tones.size}) for this tone "
                f"plan, got {tx_symbols.shape}")
    else:
        labels = rng.integers(0, config.qam_order,
                              size=(config.n_symbols, config.n_active))
        tx_symbols = qam_modulate(labels, config.qam_order)

    # Zero-padded IFFT implements ideal oversampling.
    freq = np.zeros((config.n_symbols, os_nfft), dtype=complex)
    freq[:, tones % os_nfft] = tx_symbols
    time = np.fft.ifft(freq, axis=1) * os_nfft / np.sqrt(config.n_active)

    with_cp = np.concatenate([time[:, -cp:], time], axis=1)

    # Raised-cosine symbol windowing with overlap-add, as in real 802.11
    # transmitters, to suppress sinc sidelobes. The ramps only touch the
    # first `w` CP samples and a cyclic postfix, never the FFT window, so
    # demodulation stays exact.
    w = config.window_len * config.oversampling
    sym_len = with_cp.shape[1]
    if w > 0:
        ramp = 0.5 * (1 - np.cos(np.pi * (np.arange(w) + 0.5) / w))
        ext = np.concatenate([with_cp, with_cp[:, cp:cp + w]], axis=1)
        ext[:, :w] *= ramp
        ext[:, sym_len:] *= ramp[::-1]
        x = np.zeros(config.n_symbols * sym_len + w, dtype=complex)
        for i in range(config.n_symbols):
            x[i * sym_len: i * sym_len + sym_len + w] += ext[i]
        x = x[: config.n_symbols * sym_len]
    else:
        x = with_cp.reshape(-1)

    scale = np.sqrt(np.mean(np.abs(x) ** 2))
    x = x / scale
    return OFDMWaveform(x=x, tx_symbols=tx_symbols, config=config,
                        scale=scale, tone_indices=tones)


def demodulate_ofdm(y: np.ndarray, ref: OFDMWaveform) -> np.ndarray:
    """Demodulate samples aligned with ``ref`` back to constellation points.

    Returns an (n_symbols, n_active) array. No equalization is applied here;
    metric functions decide how to normalize (scalar or per-tone).
    """
    cfg = ref.config
    os_nfft = cfg.fft_size * cfg.oversampling
    cp = cfg.cp_len * cfg.oversampling
    sym_len = os_nfft + cp
    n_sym = len(y) // sym_len
    if n_sym < cfg.n_symbols:
        raise ValueError("signal shorter than the reference waveform")

    blocks = y[: cfg.n_symbols * sym_len].reshape(cfg.n_symbols, sym_len)
    freq = np.fft.fft(blocks[:, cp:], axis=1)
    rx = freq[:, ref.tone_indices % os_nfft]
    # Undo generation scaling so a distortion-free loopback returns
    # tx_symbols exactly.
    rx *= ref.scale * np.sqrt(cfg.n_active) / os_nfft
    return rx


# papr_db lives in wifitrx.units (one definition; this module re-exports it
# so ``from wifitrx.waveform import papr_db`` keeps working)
