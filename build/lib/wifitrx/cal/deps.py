"""Declarative calibration-ordering constraints, validated before measurement.

The canonical sequence in ``sequence.run_full_cal`` encodes ordering rules
that exist for physical reasons, not tidiness: running a step before its
prerequisite does not fail loudly — it *converges on the wrong answer*
(e.g. TX IQ cal run before RX IQ cal exists is fine, but RX IQ cal run
before TX IQ cal makes the estimator absorb the TX image into the RX
corrector: the loopback image nulls while the over-the-air image gets
worse).  A comment next to the call site cannot protect against a caller
reordering steps, so the rules live here as data and are checked *at plan
time, before any capture is taken*.
"""
from __future__ import annotations

# step -> {required-earlier-step: reason it must come first}
STEP_REQUIRES: dict[str, dict[str, str]] = {
    "tx_lo_leak_loopback": {
        "tx_lpf_corner": "leak/pilot tones are measured on FFT bins; an "
                         "uncalibrated TX passband corner skews the tone "
                         "ratio the transfer-gain estimate relies on",
        "rx_lpf_corner": "same capture path: RX passband distortion "
                         "pollutes every frequency-domain estimate",
        "rx_dc_offset": "the RX-LO offset separates TX leak from RX DC in "
                        "frequency, but an unpurged gain-dependent RX DC "
                        "still leaks into neighbouring bins via spectral "
                        "leakage at short capture lengths",
    },
    "rx_iip2": {
        "tx_lo_leak_loopback": "the PA third-order product tone2 x leak x "
                               "conj(tone1) lands exactly on the (f2 - f1) "
                               "IM2 measurement bin; with an uncalibrated "
                               "carrier leak it buries the IM2 null by "
                               "~35 dB",
    },
    "tx_iq": {
        "tx_lpf_corner": "per-tone rho(f) is an FFT-bin ratio; passband "
                         "droop must already be at its calibrated corner",
        "rx_lpf_corner": "the observation path's passband droop enters the "
                         "same per-tone bin ratios rho(f) is built from",
        "loopback_delay": "FFT-bin calibrations need capture alignment; "
                          "un-aligned captures rotate rho(f) per tone",
    },
    "group_delay": {
        "tx_iq": "the group-delay check consumes rho(f) estimated by tx_iq",
    },
    "rx_iq": {
        "tx_iq": "RX IQ cal sends single-sideband combs through the TX and "
                 "attributes any image to the RX; a residual TX image "
                 "biases W2 so the pair converges on TX-cancels-RX: the "
                 "loopback image nulls while the antenna-side image grows",
        "loopback_delay": "FFT-bin calibration needs capture alignment",
    },
    "dpd": {
        "tx_iq": "ILA fits whatever distortion it observes; residual IQ "
                 "image would be learned into the GMP coefficients and "
                 "re-applied at every drive level",
        "tx_lo_leak_loopback": "residual carrier leak likewise gets learned "
                               "into the predistorter as a DC term",
        "tx_power": "DPD trains at the final operating drive, which "
                    "tx_power establishes; training at the wrong drive "
                    "point misplaces the compression inverse",
    },
}


def validate_order(names: list[str]) -> None:
    """Raise ValueError if the planned step order violates STEP_REQUIRES.

    A step's requirement must be present *and* earlier.  Call this on the
    planned name list before the first capture — mis-ordered calibrations
    converge on wrong answers rather than failing, so runtime is too late.
    """
    seen: set[str] = set()
    for name in names:
        for req, reason in STEP_REQUIRES.get(name, {}).items():
            if req not in seen:
                where = "runs after" if req in names else "is missing for"
                raise ValueError(
                    f"calibration order invalid: '{req}' {where} '{name}'. "
                    f"Why '{req}' must come first: {reason}")
        seen.add(name)


# steps whose programmed correction drifts with temperature (a modeled
# tempco exists for the underlying impairment) — the ones a
# temperature-triggered recalibration must re-run
TEMP_SENSITIVE: dict[str, str] = {
    "tx_lpf_corner": "RC tempco moves the corner off the calibrated code",
    "rx_lpf_corner": "RC tempco moves the corner off the calibrated code",
    "tx_lo_leak_loopback": "the leak null is amplitude-matched at the "
                           "calibration temperature; drift in either "
                           "direction un-nulls it",
    "tx_iq": "quadrature phase drifts with LO buffer delay tempco",
    "rx_iq": "quadrature phase drifts with LO buffer delay tempco",
    "tx_power": "driver gain tempco shifts the code -> dBm table",
    "dpd": "the PA drive point shifts with driver gain drift (AdaptiveDPD "
           "tracks this at runtime when enabled; a recal replaces stale "
           "coefficients)",
}


def recal_steps(executed: list[str]) -> list[str]:
    """Minimal re-run list after temperature leaves the hold range.

    The temperature-sensitive steps that were in the original run, plus
    (transitively) the prerequisites needed to measure them — e.g.
    loopback_delay for the FFT-bin calibrations, rx_dc_offset for the
    LO-leak method — in the original order, re-validated against
    STEP_REQUIRES so the shortcut sequence cannot silently break the
    ordering physics.
    """
    want = {s for s in executed if s in TEMP_SENSITIVE}
    grew = True
    while grew:
        grew = False
        for s in list(want):
            for req in STEP_REQUIRES.get(s, {}):
                if req in executed and req not in want:
                    want.add(req)
                    grew = True
    plan = [s for s in executed if s in want]
    validate_order(plan)
    return plan


def planned_steps(prof: dict, with_iip2: bool, with_dpd: bool) -> list[str]:
    """The step-name plan run_full_cal will execute for these switches.

    Kept next to the rules so the plan can be validated before measurement
    and cross-checked against the executed CalResult names afterwards.
    """
    names = ["tx_lpf_corner", "rx_lpf_corner", "rx_dc_offset"]
    if prof["envdet_leak"]:
        names.append("tx_lo_leak_envdet")
    names.append("tx_lo_leak_loopback")
    if with_iip2:
        names.append("rx_iip2")
    names += ["loopback_delay", "tx_iq", "group_delay", "rx_iq", "tx_power"]
    if with_dpd:
        names.append("dpd")
    names += ["agc_sweep", "final_loopback_evm"]
    return names
