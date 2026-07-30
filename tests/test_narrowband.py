"""Narrow-mode (20 MHz) regressions.

Found via an anomalous GUI run: 20 MHz calibrated to only −32 dB while
320 MHz reached −44 dB.  Two independent causes, both pinned here:

1. The GI is fixed in absolute time while the LPF impulse response
   scales as 1/BW — a wide-mode 1.3×BW/2 corner rings past the GI at
   20 MHz and floors EVM near −33 dB (ISI, uncorrectable by per-tone
   EQ).  ``recommended_lpf_corner_hz`` relaxes narrow modes to 3×.
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
    assert recommended_lpf_corner_hz(20e6, "tx") == pytest.approx(30e6)
    assert recommended_lpf_corner_hz(40e6, "rx") == pytest.approx(60e6)


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
    # 1024-QAM needs ~-35 dB TX EVM; the old floor was -32.6,
    # the 3x corner policy lands ~-41
    assert r.metrics["tx_evm_db"] <= -40.0, r.metrics
    assert r.metrics["loopback_evm_db"] <= -37.0, r.metrics


# --------------------------------------------------- legacy 11ac numerology
def _lpf_only_evm(cfg, ratio):
    from wifitrx.cal.sequence import tx_evm
    from wifitrx.chain import TxChain, TxParams
    from wifitrx.impairments.analog_filter import TunableLPF
    from wifitrx.impairments.converters import DACParams
    from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
    from wifitrx.impairments.phase_noise import LOModel
    bw = cfg.bandwidth_hz
    p = TxParams(bandwidth_hz=bw, dac=DACParams(enabled=False),
                 lpf=TunableLPF(fc_nominal_hz=bw / 2 * ratio),
                 iq=FreqDepIQImbalance(enabled=False), lo_leak_dbm=None,
                 lo=LOModel(enabled=False), pa_enabled=False)
    return tx_evm(TxChain(p, cfg.sample_rate_hz), cfg, drive_scale=0.12)


def test_wifi5_numerology_properties():
    from wifitrx.waveform import OFDMConfig
    cfg = OFDMConfig(bandwidth_hz=20e6, subcarrier_spacing_hz=312.5e3,
                     cp_fraction=1 / 4, n_symbols=4)
    assert cfg.fft_size == 64
    assert cfg.n_active == 52          # 11a/n/ac 20 MHz occupancy
    assert cfg.cp_len == 16            # 0.8 us long GI at 20 MHz
    assert OFDMConfig(bandwidth_hz=20e6, subcarrier_spacing_hz=312.5e3,
                      cp_fraction=1 / 8, n_symbols=4).cp_len == 8
    # 11ax table untouched by the numerology parameter
    assert OFDMConfig(bandwidth_hz=20e6, n_symbols=4).n_active == 242


def test_wifi5_lpf_floor_beats_wifi7_at_same_corner():
    """Counterintuitive but measured: at the same corner the legacy
    numerology suffers LESS from the LPF — its 52-tone occupancy stops at
    0.81×BW/2 (away from the dispersive corner region) and its window is
    proportionally shorter, leaving more absolute GI margin; both beat
    the 4× shorter symbol's larger relative ISI cost."""
    from wifitrx.waveform import OFDMConfig
    bw = 20e6
    ax = OFDMConfig(bandwidth_hz=bw, qam_order=1024, n_symbols=6,
                    oversampling=4)
    ac = OFDMConfig(bandwidth_hz=bw, qam_order=256, n_symbols=12,
                    oversampling=4, subcarrier_spacing_hz=312.5e3,
                    cp_fraction=1 / 4)
    evm_ax = _lpf_only_evm(ax, 1.3)
    evm_ac = _lpf_only_evm(ac, 1.3)
    assert evm_ac < evm_ax - 3.0, (evm_ac, evm_ax)


@pytest.mark.slow
def test_wifi5_20mhz_full_cal():
    """802.11ac 20 MHz long-GI end to end under the 3x corner policy."""
    from specs import _chains
    from wifitrx.cal.sequence import run_full_cal
    from wifitrx.chain import LoopbackPath
    from wifitrx.waveform import OFDMConfig

    cfg = OFDMConfig(bandwidth_hz=20e6, qam_order=256, n_symbols=24,
                     oversampling=4, subcarrier_spacing_hz=312.5e3,
                     cp_fraction=1 / 4)
    tx, rx = _chains(20e6, 5, cfg.sample_rate_hz)
    res = run_full_cal(tx, rx, cfg, LoopbackPath(atten_db=40.0, delay_ns=6.0),
                       with_dpd=True)
    final = {r.name: r for r in res}["final_loopback_evm"]
    for r in res:
        assert r.passed in (True, None), (r.name, r.metrics_after)
    # 11ac MCS9 (256-QAM 5/6) needs -32 dB; we land ~-44
    assert final.metrics_after["tx_evm_db"] <= -40.0, final.metrics_after
