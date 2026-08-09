"""What each delivered residual means, shipped inside the cal-state file.

``irr_min_db: 55.7`` is useless on its own: is larger better, over what
bandwidth is it the worst case, and — the question that actually decides
whether the recipient's link simulation is right — *how is it injected*?
An image-rejection figure applied as a gain imbalance produces a
different constellation than the same dB applied as a quadrature error.
The answer has to travel in the JSON, because the consumer has a file
and a link simulator, not this repository.

Every entry carries:

* ``unit`` / ``meaning`` / ``better`` — what the number is;
* ``apply`` — the formula-level recipe a link simulation uses to consume
  it.  This text is the contract the replay harness
  (:mod:`wifitrx.handoff.replay`) executes literally;
* ``role`` — the machine-readable consumption class, which is what lets
  a replay account for **every** key instead of silently skipping the
  awkward ones:

  - ``impairment``: injectable into a waveform per ``apply``;
  - ``figure``: an accuracy/verification figure about the calibration
    itself — real information, but injecting it would double-count
    something already inside another number;
  - ``condition``: a measured property of the setup (e.g. the loopback
    delay) — not an impairment of the part;
  - ``total``: a measured whole.  Never injected: a total re-applied as
    a term would make any closure check circular by construction.

* ``plane`` — which measurement plane the figure lives on: ``tx`` (PA
  output), ``rx`` (through the receiver), ``loopback`` (the composite
  path).  The replay filters on it, so transmit keys stay out of the
  receive closure and vice versa — v0.4.0 applied the receive image to
  a PA-output target for want of exactly this field.

**The spec is the lift list.**  ``extract_residuals`` ships exactly the
keys named here; everything else stays inside its step summary.  The
guard against this table drifting from what the sequence measures is a
test (``tests/test_residual_spec.py``), not a runtime warning on every
file.

``DUPLICATES`` declares pairs that describe one physical quantity
measured two ways, as data rather than prose, so a consumer (and the
replay) can apply at most one *and name the one it dropped*.
"""
from __future__ import annotations

from typing import Any

#: Pairs (a, b) that are two observations of the same physical quantity;
#: apply at most one — ``b`` is the one to keep (finer instrument).
DUPLICATES: tuple[tuple[str, str], ...] = (
    ("tx_lo_leak_envdet.lo_leak_dbc", "tx_lo_leak_loopback.lo_leak_dbc"),
)

RESIDUAL_SPEC: dict[str, dict[str, str]] = {
    "tx_lpf_corner.fc_hz": {
        "plane": "tx",
        "unit": "Hz",
        "meaning": "TX baseband corner as tuned (target 1.3 x BW/2, the "
                   "DPD bandwidth)",
        "better": "n/a — a design target, not a defect",
        "role": "impairment",
        "apply": "5th-order Butterworth magnitude response at this corner "
                 "on the transmit side. A per-tone-equalized receiver "
                 "removes it entirely; carry it only for unequalized "
                 "consumers or absolute-power work.",
    },
    "tx_lpf_corner.fc_err_pct": {
        "plane": "tx",
        "unit": "%",
        "meaning": "corner tuning error relative to its target",
        "better": "smaller magnitude",
        "role": "figure",
        "apply": "do not inject — the achieved corner fc_hz already "
                 "contains this error.",
    },
    "rx_lpf_corner.fc_hz": {
        "plane": "rx",
        "unit": "Hz",
        "meaning": "RX channel-select corner as tuned (target 1.12 x BW/2)",
        "better": "n/a — a design target, not a defect",
        "role": "impairment",
        "apply": "5th-order Butterworth magnitude response at this corner "
                 "on the receive side, before the equalizer. Same "
                 "per-tone-EQ caveat as the TX corner.",
    },
    "rx_lpf_corner.fc_err_pct": {
        "plane": "rx",
        "unit": "%",
        "meaning": "corner tuning error relative to its target",
        "better": "smaller magnitude",
        "role": "figure",
        "apply": "do not inject — fc_hz already contains it.",
    },
    "rx_dc_offset.worst_dc_dbfs": {
        "plane": "rx",
        "unit": "dBFS",
        "meaning": "residual DC at the ADC input after analog coarse + "
                   "digital fine correction, worst across the 8 AGC states",
        "better": "more negative",
        "role": "impairment",
        "apply": "add a complex constant at (worst_dc_dbfs + "
                 "adc_backoff_db) dB relative to signal power — the "
                 "conversion from full-scale-relative to signal-relative "
                 "needs the conditions block's adc_backoff_db. The "
                 "constant lands on subcarrier zero, which 802.11be "
                 "leaves unmodulated, so data-tone EVM is structurally "
                 "almost blind to it; it prices receiver dynamic range, "
                 "not constellation error.",
    },
    "rx_dc_offset.worst_dc_dbfs_after_analog": {
        "plane": "rx",
        "unit": "dBFS",
        "meaning": "residual DC after the analog coarse stage alone, "
                   "worst state — the headroom the digital fine stage "
                   "works inside",
        "better": "more negative",
        "role": "figure",
        "apply": "do not inject — superseded by worst_dc_dbfs, which is "
                 "the shipped end state.",
    },
    "tx_lo_leak_envdet.lo_leak_dbc": {
        "plane": "tx",
        "unit": "dBc",
        "meaning": "TX carrier leakage at the PA output relative to "
                   "signal power, measured by the envelope detector",
        "better": "more negative",
        "role": "impairment",
        "apply": "add the complex constant c with |c|^2 = 10^(dBc/10) x "
                 "signal power, before the channel. Same DC-bin caveat "
                 "as the RX DC: near-zero for 11be data-tone EVM, real "
                 "for the spectral mask. Duplicate of the loopback "
                 "measurement — apply at most one of the pair.",
    },
    "tx_lo_leak_loopback.lo_leak_dbc": {
        "plane": "tx",
        "unit": "dBc",
        "meaning": "TX carrier leakage at the PA output relative to "
                   "signal power, measured through the loopback receiver "
                   "(the finer of the two instruments)",
        "better": "more negative",
        "role": "impairment",
        "apply": "same recipe as the envelope-detector entry; this is "
                 "the one to keep when applying.",
    },
    "rx_iip2.iip2_dbm": {
        "plane": "rx",
        "unit": "dBm",
        "meaning": "receive IIP2 after trim (mixer even-order null)",
        "better": "larger",
        "role": "impairment",
        "apply": "matters only with a blocker present: the IM2 pseudo-"
                 "baseband product sits at P_IM2 = 2 x P_blocker - IIP2 "
                 "(all dBm at the same reference plane). Without a "
                 "blocker there is nothing to inject — a clean-channel "
                 "EVM replay must list this key as not consumed, with "
                 "this reason.",
    },
    "loopback_delay.delay_ns": {
        "plane": "loopback",
        "unit": "ns",
        "meaning": "measured loopback path delay, used to align "
                   "calibration captures",
        "better": "n/a — a property of the test path, not of the part",
        "role": "condition",
        "apply": "do not inject — instrument alignment, already "
                 "compensated inside every measurement in this file.",
    },
    "tx_iq.irr_min_db": {
        "plane": "tx",
        "unit": "dB",
        "meaning": "TX image rejection after the frequency-dependent "
                   "correction, worst tone across the occupied band",
        "better": "larger",
        "role": "impairment",
        "apply": "inject the widely-linear response y = u + g*conj(u) "
                 "with |g| = 10^(-irr_min_db/20), before the channel. "
                 "The residual is frequency dependent and this is its "
                 "worst point, so a flat figure is conservative.",
    },
    "rx_iq.irr_min_db": {
        "plane": "rx",
        "unit": "dB",
        "meaning": "RX image rejection after the frequency-dependent "
                   "correction, worst tone, at the calibrated AGC state",
        "better": "larger",
        "role": "impairment",
        "apply": "same widely-linear form as the TX entry, applied after "
                 "the channel rather than before it.",
    },
    "group_delay.estimated_ps": {
        "plane": "tx",
        "unit": "ps",
        "meaning": "the I/Q rail group-delay mismatch the estimator "
                   "measured and the wideband w2 FIR absorbed",
        "better": "n/a — an estimate of the part, not a defect left in",
        "role": "figure",
        "apply": "do not inject — the w2 correction already absorbs "
                 "this; what it missed is error_ps, the entry below.",
    },
    "group_delay.error_ps": {
        "plane": "tx",
        "unit": "ps",
        "meaning": "residual I/Q rail group-delay estimate error (the "
                   "wideband w2 FIR absorbs the mismatch itself; this is "
                   "what the dedicated estimator missed)",
        "better": "smaller magnitude",
        "role": "impairment",
        "apply": "delay the I rail by |error_ps| against Q (fractional "
                 "delay). Attributing all of it to one rail is the "
                 "worst-case reading of an unsigned residual.",
    },
    "dpd.evm_db": {
        "plane": "tx",
        "unit": "dB",
        "meaning": "PA-output EVM after predistortion at the calibration "
                   "drive level — the in-band distortion the amplifier "
                   "still does, plus the transmit floor. This is the "
                   "dominant in-band term; a residual list without it "
                   "reads 10+ dB optimistic",
        "better": "more negative",
        "role": "impairment",
        "apply": "add a complex Gaussian error at this level relative to "
                 "signal power (the number is a per-tone-equalized "
                 "measurement). Valid at the calibration drive; "
                 "predistortion interacts with drive level, so re-derive "
                 "before using it far from that operating point.",
    },
    "dpd.aclr_worst_dbc": {
        "plane": "tx",
        "unit": "dBc",
        "meaning": "worst adjacent-channel leakage ratio after DPD",
        "better": "more negative",
        "role": "figure",
        "apply": "a spectral figure — consumed by coexistence budgets, "
                 "not by an in-band EVM replay.",
    },
    "agc_sweep.worst_landing_err_db": {
        "plane": "rx",
        "unit": "dB",
        "meaning": "worst ADC landing-level error across the AGC ladder "
                   "sweep",
        "better": "smaller magnitude",
        "role": "figure",
        "apply": "do not inject — verification of the servo; its effect "
                 "is already inside every receive-side figure.",
    },
    "agc_sweep.min_snr_db_above_-50dBm": {
        "plane": "rx",
        "unit": "dB",
        "meaning": "minimum post-chain SNR over inputs above -50 dBm "
                   "during the AGC verification sweep",
        "better": "larger",
        "role": "figure",
        "apply": "do not inject — a verification aggregate over the "
                 "sweep, not a single operating point.",
    },
    "final_loopback_evm.evm_db": {
        "plane": "loopback",
        "unit": "dB",
        "meaning": "composite TX+RX loopback EVM, shared LO (phase noise "
                   "cancels in this view)",
        "better": "more negative",
        "role": "total",
        "apply": "never inject a total: re-applying it as a term makes "
                 "any closure check pass by construction.",
    },
    "final_loopback_evm.tx_evm_db": {
        "plane": "tx",
        "unit": "dB",
        "meaning": "PA-output EVM at the 802.11be TX measurement point "
                   "(per-tone EQ + CPE removal) — the closure target the "
                   "replay compares against",
        "better": "more negative",
        "role": "total",
        "apply": "never inject — this is the measured whole the "
                 "impairment entries are supposed to explain.",
    },
    "final_loopback_evm.rx_evm_db": {
        "plane": "rx",
        "unit": "dB",
        "meaning": "ideal waveform through the impaired RX at the "
                   "loopback's coupled level, independent LO (phase "
                   "noise counts in full)",
        "better": "more negative",
        "role": "total",
        "apply": "never inject — measured whole of the receive view.",
    },
    "final_loopback_evm.rx_input_dbm": {
        "plane": "rx",
        "unit": "dBm",
        "meaning": "the RF input level rx_evm_db (and the two figures "
                   "below) were measured at — the level the loopback "
                   "path actually delivers",
        "better": "n/a — an operating point, not a defect",
        "role": "condition",
        "apply": "not injected itself; the noise recipe below converts "
                 "through it. Receive figures far from this level need "
                 "a re-measurement, not a scaling.",
    },
    "final_loopback_evm.rx_gain_state": {
        "plane": "rx",
        "unit": "index",
        "meaning": "the AGC gain state that level lands on — the "
                   "receive figures are properties of this state, not "
                   "of the die",
        "better": "n/a",
        "role": "condition",
        "apply": "not injected; it names which state the NF and phase "
                 "figures describe.",
    },
    "final_loopback_evm.rx_nf_db": {
        "plane": "rx",
        "unit": "dB",
        "meaning": "effective noise figure at that state, measured "
                   "idle-channel through the whole chain (LNA to "
                   "digital out) — absorbs thermal, quantization and "
                   "correction residue, which is why it is the number "
                   "to replay rather than the ladder's Friis entry",
        "better": "smaller",
        "role": "impairment",
        "apply": "add complex AWGN at SNR = rx_input_dbm - (-174 + "
                 "rx_nf_db + 10log10(BW)) dB relative to signal power.",
    },
    "final_loopback_evm.rx_im3_dbc": {
        "plane": "rx",
        "unit": "dBc",
        "meaning": "two-tone third-order product at that state and "
                   "total level, per tone, worst of 2f1-f2 / 2f2-f1 — "
                   "the receive view's in-band distortion, the term "
                   "whose absence the replay closure exposed",
        "better": "more negative",
        "role": "impairment",
        "apply": "apply the memoryless cubic y + c*y*|y|^2 with "
                 "c = (8/3) * 10^(rx_im3_dbc/20) on the unit-power "
                 "waveform: c is chosen so two equal tones at the same "
                 "total power reproduce the measured ratio, and the "
                 "OFDM statistics do the rest. Valid near "
                 "rx_input_dbm; distortion scales 2 dB per dB of "
                 "drive, so far from that level re-measure.",
    },
    "final_loopback_evm.rx_phase_err_dbc": {
        "plane": "rx",
        "unit": "dBc",
        "meaning": "integrated post-tracking phase error at that state "
                   "and level: what the angle costs after per-symbol "
                   "common-phase and frequency tracking. Not pure LO "
                   "phase noise — whatever the delivered state puts in "
                   "the angle (residual per-state IQ, spurs) is "
                   "included, deliberately",
        "better": "more negative",
        "role": "impairment",
        "apply": "multiply by exp(j*phi), phi zero-mean Gaussian with "
                 "variance 10^(dBc/10). The spectral shape is not "
                 "shipped; a consumer needing the profile takes it "
                 "from circuit data, not from this figure.",
    },
}


def run_conditions(cfg, tx=None, rx=None, *, with_dpd: bool | None = None,
                   profile: str | None = None) -> dict:
    """The measurement context a consumer needs, from the run's objects.

    One implementation shared by every writer, because the failure mode
    of per-caller dicts is a file that records the recipe it did not
    use.  The waveform fields are what lets a recipient *regenerate the
    stimulus* — without them the captures and residuals in the file
    cannot be checked from outside; ``adc_backoff_db`` is the constant
    the DC recipes convert through; the filter orders are what the
    corner recipes mean by "Butterworth at this corner".
    """
    cond = {
        "bandwidth_hz": float(cfg.bandwidth_hz),
        "qam_order": int(cfg.qam_order),
        "n_symbols": int(cfg.n_symbols),
        "subcarrier_spacing_hz": float(cfg.subcarrier_spacing_hz),
        "waveform_seed": cfg.seed,
        "oversampling": int(cfg.oversampling),
        # the loopback shares one LO between TX and RX, so the composite
        # evm_db is blind to phase noise; the rx_evm_db view is not
        "shared_lo_loopback": True,
    }
    if tx is not None:
        cond["tx_lpf_order"] = int(tx.params.lpf.order)
        cond["tx_lpf_family"] = str(tx.params.lpf.family)
    if rx is not None:
        cond["rx_lpf_order"] = int(rx.params.lpf.order)
        cond["rx_lpf_family"] = str(rx.params.lpf.family)
        cond["adc_backoff_db"] = float(rx.params.adc_backoff_db)
    if with_dpd is not None:
        cond["with_dpd"] = bool(with_dpd)
    if profile is not None:
        cond["profile"] = str(profile)
    return cond


def extract_residuals(results: list[dict]) -> dict[str, Any]:
    """The flat residual surface of a run: exactly the specced keys.

    Returns ``{"values", "specification", "duplicates"}`` ready for
    embedding.  ``specification`` carries only entries for keys that are
    actually present, so a file never describes numbers it does not
    ship; ``duplicates`` carries only pairs shipped in full.
    """
    values: dict[str, Any] = {}
    for r in results:
        step = r.get("name") if isinstance(r, dict) else r.name
        after = (r.get("metrics_after") if isinstance(r, dict)
                 else r.metrics_after) or {}
        for metric, value in after.items():
            key = f"{step}.{metric}"
            if key in RESIDUAL_SPEC:
                values[key] = value
    return {
        "values": values,
        "specification": {k: RESIDUAL_SPEC[k] for k in values},
        "duplicates": [list(pair) for pair in DUPLICATES
                       if all(k in values for k in pair)],
    }
