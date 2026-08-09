"""Consume a cal-state file from the outside, the way its recipient will.

Every other module measures the part.  This one deliberately does not:
it reads ``cal_state.json``, follows each residual entry's ``apply``
recipe **to the letter** on a clean waveform, and asks whether the EVM
that comes out is the EVM the file itself reports.  Nothing here imports
:mod:`wifitrx.chain` or :mod:`wifitrx.cal` — if it did, it would be
checking the model against itself, which is the one thing a delivery
review cannot do.

This is the only check in the suite that can catch an **omission**.  The
per-step verdicts judge the numbers that exist; a residual that was
never shipped at all passes every one of them.  The peer project this
harness is modeled on found a 14.4 dB omission exactly this way — and
then defeated its own check by shipping a fallback term *solved from the
measured EVM*, after which the closure held by construction: a bundle
with five falsified residuals still closed to 0.14 dB.  Hence the two
rules this module is built around:

* **No term in the closure sum may be derived from the closure target.**
  Every number applied here is an independent measurement from its own
  calibration step.  ``dpd.evm_db`` — an EVM figure — is legitimate
  under this rule because the DPD step measured it at the PA output
  before the final scoring existed; it is compared *against* the final
  number, not solved from it.  Because it dominates the sum, the result
  also reports the calibration-artifact-only row (everything except it),
  so a reader sees what the small terms explain on their own.
* **Every key is accounted for.**  ``residuals.values`` keys come back
  applied, skipped-with-reason (from the spec's own ``role``), dropped
  as a declared duplicate (named, from the file's ``duplicates`` list),
  or — loudly — ``no_recipe``, which is a defect in this module rather
  than in the file.  Silence is the failure mode this table exists to
  prevent: the peer replay silently discarded the transmit image figure
  and consumed 6 of 21 keys without saying which.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import numpy as np

from ..metrics.evm import evm_of_signal
from ..waveform.ofdm import OFDMConfig, generate_ofdm

#: Per-view (low, high) acceptance band for the closure gap [dB], set
#: from a 10-seed sweep (40 MHz / 256-QAM, DPD on) rather than guessed.
#: TX measured mean -0.45, std 0.51, absmax 1.17: the spread is the
#: check's real resolution (the DPD term is measured at the cal drive
#: and re-scored on a fresh waveform).  RX after the B13 coefficient
#: fix measured mean +0.42, std 0.45, absmax 1.18 — the v0.5.0
#: "systematic rx bias" of +1.28 dB was not a missing modulation-
#: distortion term but the replay's own IM3 recipe overstating itself:
#: the real-passband 3/4 IM3 factor was applied to a complex-envelope
#: cubic (+2.5 dB in the term).  An isolation study (backlog B13)
#: pinned every isolated source to within 0.7 dB of its shipped
#: figure.  Both bands are symmetric; the sweep is the provenance.
GAP_BAND_DB = {"tx": (-2.0, 2.0), "rx": (-2.0, 2.0)}

#: Per-view closure target.  Everything with role="total" is refused as
#: an input; these keys are what each view's sum is compared against.
#: The transmit view applies plane="tx" impairments, the receive view
#: plane="rx" — v0.4.0 had one undivided pool and applied the receive
#: image to a PA-output target.
MEASURED_KEYS = {"tx": "final_loopback_evm.tx_evm_db",
                 "rx": "final_loopback_evm.rx_evm_db"}

#: The in-band distortion term: independent, but dominant — reported
#: both inside the full sum and excluded from the second row.
DISTORTION_KEY = "dpd.evm_db"

#: impairment-role keys this replay knows it cannot inject, with the
#: reason a recipient needs.  A key in neither this table nor
#: ``_INJECTORS`` is reported as ``no_recipe`` — never skipped silently.
NOT_INJECTABLE = {
    "rx_iip2.iip2_dbm": "needs a blocker: the IM2 product is "
                        "2*P_blocker - IIP2, and a clean-channel replay "
                        "has no blocker to raise it above nothing",
}


@dataclass
class ReplayResult:
    """The three-number closure plus the full key accounting."""

    view: str
    explained_evm_db: float
    explained_cal_only_db: float
    measured_evm_db: float
    gap_db: float
    #: measured power minus explained power, as dB EVM; None when the
    #: replay over-explains (explained above measured)
    unexplained_evm_db: float | None
    verdict: str                       # "consistent" | "gap"
    terms_db: dict[str, float] = field(default_factory=dict)
    #: every residuals.values key -> {"status", "reason"}
    accounting: dict[str, dict] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"== {self.view.upper()} view ==",
            f"explained (all terms)      {self.explained_evm_db:8.2f} dB",
            f"explained (cal terms only) {self.explained_cal_only_db:8.2f} dB",
            f"measured  ({MEASURED_KEYS[self.view]}) "
            f"{self.measured_evm_db:8.2f} dB",
            f"gap                        {self.gap_db:+8.2f} dB"
            f"  -> {self.verdict}",
        ]
        if self.unexplained_evm_db is not None:
            lines.append(
                f"unexplained residual       "
                f"{self.unexplained_evm_db:8.2f} dB")

        lines.append("")
        lines.append("per-term (each applied alone):")
        for key, value in sorted(self.terms_db.items(),
                                 key=lambda kv: kv[1], reverse=True):
            lines.append(f"  {key:36s} {value:8.2f} dB")
        lines.append("")
        lines.append("key accounting:")
        for key, entry in sorted(self.accounting.items()):
            lines.append(f"  [{entry['status']:17s}] {key}: "
                         f"{entry['reason']}")
        return "\n".join(lines)


# ---- injection primitives (the `apply` recipes, executed) -------------

def _image(y: np.ndarray, irr_db: float) -> np.ndarray:
    """Widely-linear y + g*conj(y), |g| = 10^(-irr/20)."""
    return y + 10.0 ** (-float(irr_db) / 20.0) * np.conj(y)


def _add_dc_dbc(y: np.ndarray, dbc: float) -> np.ndarray:
    """A complex constant at ``dbc`` relative to signal power."""
    p = float(np.mean(np.abs(y) ** 2))
    return y + np.sqrt(10.0 ** (float(dbc) / 10.0) * p)


def _skew_i_rail(y: np.ndarray, tau_s: float, fs: float) -> np.ndarray:
    """Delay the I rail by ``tau_s`` against Q (fractional, via FFT)."""
    n = y.size
    f = np.fft.fftfreq(n, d=1.0 / fs)
    ramp = np.exp(-2j * np.pi * f * float(tau_s))
    i_delayed = np.fft.ifft(np.fft.fft(y.real) * ramp)
    return i_delayed.real + 1j * y.imag


def _butterworth_droop(y: np.ndarray, fc_hz: float, fs: float,
                       order: int) -> np.ndarray:
    """Magnitude-only Butterworth droop at ``fc_hz`` (per-tone EQ
    removes the phase anyway; the magnitude is what an unequalized
    consumer would keep)."""
    n = y.size
    f = np.fft.fftfreq(n, d=1.0 / fs)
    mag = 1.0 / np.sqrt(1.0 + (f / float(fc_hz)) ** (2 * int(order)))
    return np.fft.ifft(np.fft.fft(y) * mag)


def _additive_error(y: np.ndarray, evm_db: float,
                    seed: int = 0) -> np.ndarray:
    """Complex Gaussian error at ``evm_db`` relative to signal power."""
    rng = np.random.default_rng(seed)
    p = float(np.mean(np.abs(y) ** 2))
    scale = np.sqrt(10.0 ** (float(evm_db) / 10.0) * p / 2.0)
    return y + scale * (rng.standard_normal(y.size)
                        + 1j * rng.standard_normal(y.size))


def _injectors(cond: dict, values: dict) -> dict:
    """Key -> injection closure, built against the file's conditions.

    The two receive figures convert through the file's own operating
    point (``rx_input_dbm``) — that is what the condition-role key is
    in the bundle *for*.
    """
    backoff = cond.get("adc_backoff_db")
    p_in = values.get("final_loopback_evm.rx_input_dbm")
    bw = cond.get("bandwidth_hz")
    out = {
        "tx_iq.irr_min_db": lambda y, v, fs: _image(y, v),
        "rx_iq.irr_min_db": lambda y, v, fs: _image(y, v),
        "tx_lo_leak_loopback.lo_leak_dbc":
            lambda y, v, fs: _add_dc_dbc(y, v),
        "tx_lo_leak_envdet.lo_leak_dbc":
            lambda y, v, fs: _add_dc_dbc(y, v),
        "group_delay.error_ps":
            lambda y, v, fs: _skew_i_rail(y, abs(v) * 1e-12, fs),
        "tx_lpf_corner.fc_hz":
            lambda y, v, fs: _butterworth_droop(
                y, v, fs, cond.get("tx_lpf_order", 5)),
        "rx_lpf_corner.fc_hz":
            lambda y, v, fs: _butterworth_droop(
                y, v, fs, cond.get("rx_lpf_order", 5)),
        DISTORTION_KEY:
            lambda y, v, fs: _additive_error(
                y, v, seed=int(cond.get("waveform_seed") or 0) + 1),
    }
    if backoff is not None:
        out["rx_dc_offset.worst_dc_dbfs"] = (
            lambda y, v, fs: _add_dc_dbc(y, float(v) + float(backoff)))
    if p_in is not None and bw:
        def _noise(y, nf_db, fs):
            snr_db = (float(p_in)
                      - (-173.975 + float(nf_db)
                         + 10.0 * np.log10(float(bw))))
            return _additive_error(y, -snr_db,
                                   seed=int(cond.get("waveform_seed")
                                            or 0) + 2)
        out["final_loopback_evm.rx_nf_db"] = _noise
    def _im3(y, dbc, fs):
        # Cubic at 2x oversampling, then band-limit: the real chain's
        # channel filter strips the out-of-band third-order products
        # before they can alias; applied at 1x the whole 2c^2 lands
        # in-band and the term overstates itself by ~2.5 dB.
        #
        # The coefficient is the COMPLEX-ENVELOPE one: for y + c*y*|y|^2
        # two equal tones give IM3/tone = c^2 * A^4 with unit
        # combinatorial factor, so c = 2 * 10^(dBc/20).  The classic
        # real-passband 3/4 factor (c = 8/3 * sqrt(r)) does not apply
        # here — using it overstates the injected distortion by 2.5 dB,
        # which was the whole "systematic rx bias" of v0.5.0.
        c = 2.0 * 10.0 ** (float(dbc) / 20.0)
        n = y.size
        spec_lo = np.fft.fft(y)
        spec_hi = np.zeros(2 * n, dtype=complex)
        spec_hi[: n // 2] = spec_lo[: n // 2]
        spec_hi[-n // 2:] = spec_lo[-n // 2:]
        up = np.fft.ifft(spec_hi) * 2.0
        p = float(np.mean(np.abs(up) ** 2))
        up = up + c * up * (np.abs(up) ** 2) / p
        spec_hi = np.fft.fft(up)
        spec_out = np.concatenate([spec_hi[: n // 2], spec_hi[-n // 2:]])
        return np.fft.ifft(spec_out) / 2.0
    out["final_loopback_evm.rx_im3_dbc"] = _im3

    def _phase(y, dbc, fs):
        rng = np.random.default_rng(int(cond.get("waveform_seed") or 0) + 3)
        sigma = np.sqrt(10.0 ** (float(dbc) / 10.0))
        return y * np.exp(1j * sigma * rng.standard_normal(y.size))
    out["final_loopback_evm.rx_phase_err_dbc"] = _phase
    return out


# ---- the replay -------------------------------------------------------

def replay(path: str | os.PathLike, view: str = "tx") -> ReplayResult:
    """Apply the file's residuals literally; compare against its EVM.

    ``view`` selects the measurement plane: ``"tx"`` closes the
    plane="tx" impairments against the PA-output EVM, ``"rx"`` closes
    the plane="rx" impairments against the through-receiver EVM.  The
    same file must close both ways; each view can only vouch for its
    own plane's entries.

    Reads plain JSON — the recipient's view.  Raises ``ValueError`` with
    the missing piece named when the file predates the ``residuals`` or
    ``conditions`` blocks, because "cannot be replayed" is the answer a
    recipient of such a file needs to hear.
    """
    if view not in MEASURED_KEYS:
        raise ValueError(f"view must be one of {sorted(MEASURED_KEYS)}")
    measured_key = MEASURED_KEYS[view]
    doc = json.loads(open(os.fspath(path)).read())
    res = doc.get("residuals") or {}
    values = dict(res.get("values") or {})
    spec = res.get("specification") or {}
    duplicates = [tuple(p) for p in res.get("duplicates") or []]
    cond = doc.get("conditions") or {}
    if not values:
        raise ValueError("no residuals block — written before B10? "
                         "re-export the state with a current library")
    for need in ("bandwidth_hz", "qam_order", "n_symbols"):
        if need not in cond:
            raise ValueError(f"conditions block lacks {need!r}; the "
                             "stimulus cannot be regenerated, so the "
                             "residuals cannot be checked from outside")
    if measured_key not in values:
        raise ValueError(f"{measured_key} not in the file — nothing to "
                         "close the replay against")
    measured = float(values[measured_key])

    cfg = OFDMConfig(
        bandwidth_hz=float(cond["bandwidth_hz"]),
        qam_order=int(cond["qam_order"]),
        n_symbols=int(cond["n_symbols"]),
        oversampling=1,
        subcarrier_spacing_hz=float(
            cond.get("subcarrier_spacing_hz", 78.125e3)),
        seed=cond.get("waveform_seed", 0),
    )
    ref = generate_ofdm(cfg)
    fs = cfg.sample_rate_hz
    injectors = _injectors(cond, values)

    # -- accounting: settle every key's fate first, then apply ----------
    accounting: dict[str, dict] = {}
    dropped: set[str] = set()
    for first, second in duplicates:
        if first in values and second in values:
            dropped.add(first)
            accounting[first] = {
                "status": "dropped_duplicate",
                "reason": f"same physical quantity as {second}; the "
                          "file's duplicates list says apply at most "
                          "one, and the second is the finer instrument"}
    to_apply: list[str] = []
    for key in sorted(values):
        if key in accounting:
            continue
        entry = spec.get(key) or {}
        role = entry.get("role", "")
        plane = entry.get("plane")
        if role == "total":
            accounting[key] = {
                "status": "closure_target" if key == measured_key
                          else "skipped",
                "reason": "a measured whole; re-injecting it would make "
                          "closure circular by construction"}
        elif role in ("figure", "condition"):
            accounting[key] = {
                "status": "skipped",
                "reason": entry.get(
                    "apply", f"role={role}: context, not an impairment")}
        elif plane is not None and plane != view:
            accounting[key] = {
                "status": "skipped",
                "reason": f"plane={plane}: not part of the {view} "
                          "view's signal path"}
        elif plane is None:
            accounting[key] = {
                "status": "skipped",
                "reason": "no plane declared — the file predates the "
                          "view split; re-export to replay this key"}
        elif key in NOT_INJECTABLE:
            accounting[key] = {"status": "skipped",
                               "reason": NOT_INJECTABLE[key]}
        elif key in injectors:
            to_apply.append(key)
            accounting[key] = {"status": "applied",
                               "reason": "per its apply recipe"}
        else:
            accounting[key] = {
                "status": "no_recipe",
                "reason": "impairment-role key this replay cannot "
                          "inject — a defect in the replay, not in the "
                          "file"}

    def _run(keys: list[str]) -> float:
        y = np.array(ref.x, dtype=complex)
        for key in keys:
            y = injectors[key](y, float(values[key]), fs)
        return float(evm_of_signal(y, ref, equalize="per_tone").db)

    explained = _run(to_apply)
    cal_only = _run([k for k in to_apply if k != DISTORTION_KEY])
    terms = {k: _run([k]) for k in to_apply}

    gap = explained - measured
    p_meas, p_expl = 10.0 ** (measured / 10.0), 10.0 ** (explained / 10.0)
    unexplained = (10.0 * np.log10(p_meas - p_expl)
                   if p_meas > p_expl else None)
    return ReplayResult(
        view=view,
        explained_evm_db=explained,
        explained_cal_only_db=cal_only,
        measured_evm_db=measured,
        gap_db=gap,
        unexplained_evm_db=unexplained,
        verdict=("consistent"
                 if GAP_BAND_DB[view][0] <= gap <= GAP_BAND_DB[view][1]
                 else "gap"),
        terms_db=terms,
        accounting=accounting,
    )
