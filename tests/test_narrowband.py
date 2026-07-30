"""Narrow-mode (20 MHz) regressions.

Found via an anomalous GUI run: 20 MHz calibrated to only −32 dB while
320 MHz reached −44 dB.  Two independent causes, both pinned here:

1. The GI is fixed in absolute time while the LPF impulse response
   scales as 1/BW — a wide-mode 1.3×BW/2 corner rings past the GI at
   20 MHz and floors EVM near −33 dB (ISI, uncorrectable by per-tone
   EQ).  ``recommended_lpf_corner_hz`` relaxes narrow modes to 2.5×.
2. Fixed-Hz calibration probes (17/23 MHz) sit OUTSIDE a 20 MHz
   channel: the IIP2 trim walked on noise (got WORSE), the AGC sweep
   read no SNR at all.  ``scaled_probe`` scales them with bandwidth.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from wifitrx.chain.params import recommended_lpf_corner_hz  # noqa: E402
from wifitrx.waveform.stimuli import scaled_probe  # noqa: E402


def test_corner_policy_flips_with_mode():
    # wide: DPD-bandwidth tight corner (insight #2)
    assert recommended_lpf_corner_hz(320e6, "tx") == pytest.approx(208e6)
    assert recommended_lpf_corner_hz(80e6, "tx") == pytest.approx(52e6)
    # narrow: relaxed corner (insight #5) — MORE than the wide ratio
    assert recommended_lpf_corner_hz(20e6, "tx") == pytest.approx(25e6)
    assert recommended_lpf_corner_hz(40e6, "rx") == pytest.approx(50e6)


def test_probes_stay_inside_the_channel():
    for bw in (20e6, 40e6, 80e6, 160e6, 320e6):
        for f_ref in (11e6, 17e6, 23e6):
            f = scaled_probe(f_ref, bw)
            assert f <= 0.6 * bw / 2 + 1e-6 or bw >= 80e6, (bw, f_ref, f)
            assert f < bw / 2, "probe outside the channel"
        # wide modes keep the proven values untouched
        if bw >= 80e6:
            assert scaled_probe(23e6, bw) == 23e6


@pytest.mark.slow
def test_20mhz_full_cal_reaches_spec():
    """The GUI configuration that exposed the problem, end to end."""
    from specs import run_full_cal

    r = run_full_cal({"bw_mhz": 20, "qam": 1024, "seed": 5,
                      "with_dpd": True})
    by = {res.name: res for res in r.cal_state["results"]}
    # every step healthy — before the fix rx_iip2 got WORSE and
    # agc_sweep read inf
    for res in r.cal_state["results"]:
        assert res.passed in (True, None), (res.name, res.metrics_after)
    assert by["rx_iip2"].metrics_after["iip2_dbm"] > 60.0
    assert by["agc_sweep"].metrics_after["worst_landing_err_db"] < 2.5
    # 1024-QAM needs ~-35 dB TX EVM; the old floor was -32.6
    assert r.metrics["tx_evm_db"] <= -37.0, r.metrics
    assert r.metrics["loopback_evm_db"] <= -34.0, r.metrics
