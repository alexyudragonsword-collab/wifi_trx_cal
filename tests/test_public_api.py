"""The delivered surface that nothing else exercises.

These helpers are what the receiving team imports directly — plotting,
unit conversions, PAPR reduction, the preamble estimators and the
``python -m wifitrx.handoff`` CLI documented in ``docs/interface_zh.md``
— and until now the suite reached none of them: every one sat at 0-25 %
coverage.  An untested public helper is a promise nobody has checked.

Assertions stay behavioural (a CFR run really lowers PAPR, a channel
estimate really recovers the injected tilt); the figure helpers are
checked for "renders and writes a file", which is the only thing a
plotting function can honestly promise.
"""
from __future__ import annotations

import subprocess
import sys

import numpy as np
import pytest

from wifitrx.dpd import cfr_clip_filter
from wifitrx.metrics import psd
from wifitrx.metrics.amam import am_am_am_pm
from wifitrx.metrics.ccdf import ccdf
from wifitrx.metrics.irr import tone_image_irr_db
from wifitrx.units import db_to_lin, papr_db, peak_dbm, power_dbm
from wifitrx.waveform import OFDMConfig, generate_ofdm
from wifitrx.waveform.preamble import (apply_cfo, build_frame,
                                       channel_estimate, ltf_tones)


@pytest.fixture(scope="module")
def wave():
    cfg = OFDMConfig(bandwidth_hz=80e6, qam_order=256, n_symbols=4,
                     oversampling=4)
    return cfg, generate_ofdm(cfg)


# ------------------------------------------------------------------ units
def test_unit_helpers_are_mutually_consistent():
    assert db_to_lin(10.0) == pytest.approx(10.0)
    assert db_to_lin(0.0) == pytest.approx(1.0)
    x = np.array([0.3 + 0.4j, -0.5 + 0.0j])       # |x| = 0.5 both samples
    # a constant-envelope signal has equal average and peak power, so
    # peak_dbm collapses onto power_dbm and PAPR vanishes
    assert peak_dbm(x) == pytest.approx(power_dbm(x), abs=1e-9)
    assert papr_db(x) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------- metrics
def test_ccdf_is_a_decreasing_probability(wave):
    _, wf = wave
    level, prob = ccdf(wf.x)
    assert level[0] < level[-1]
    assert np.all(np.diff(prob) <= 1e-12)          # monotonically falling
    # an OFDM signal's instantaneous power is exponentially distributed,
    # so P(power > average) -> exp(-1); this is the statistics, not a
    # fitted constant
    assert prob[0] == pytest.approx(np.exp(-1.0), abs=0.03)
    assert prob[-1] < 0.01                          # almost none at the peak


def test_am_curves_recover_a_known_compression():
    x = np.linspace(1e-3, 0.5, 4000).astype(complex)
    y = x * (1 - 0.3 * np.abs(x) ** 2) * np.exp(1j * 0.8 * np.abs(x) ** 2)
    res = am_am_am_pm(x, y)
    # gain droops with drive and the phase rotates: the two defining
    # features of AM/AM + AM/PM
    assert res["gain"][0] > res["gain"][-1]
    assert res["phase_deg"][-1] - res["phase_deg"][0] > 5.0
    assert len(res["bin_r"]) == len(res["bin_gain"])


def test_tone_image_irr_reads_an_injected_imbalance():
    n, k, fs = 4096, 37, 80e6
    t = np.arange(n)
    tone = np.exp(2j * np.pi * k * t / n)
    image = 10 ** (-35 / 20) * np.exp(-2j * np.pi * k * t / n)
    irr = tone_image_irr_db(tone + image, k * fs / n, fs)
    assert irr == pytest.approx(35.0, abs=0.5)


# -------------------------------------------------------------------- CFR
def test_cfr_lowers_papr_and_keeps_the_signal_in_band(wave):
    cfg, wf = wave
    before = papr_db(wf.x)
    y = cfr_clip_filter(wf.x, target_papr_db=before - 2.0,
                        fs=cfg.sample_rate_hz, bandwidth_hz=cfg.bandwidth_hz)
    assert papr_db(y) < before - 1.0
    # average power is preserved (the PA operating point must not move)
    assert 10 * np.log10(np.mean(np.abs(y) ** 2)
                         / np.mean(np.abs(wf.x) ** 2)) == pytest.approx(
        0.0, abs=0.5)
    # and the clipping products were filtered, not left out of band
    f, p = psd(y, cfg.sample_rate_hz)
    out = p[np.abs(f) > cfg.bandwidth_hz]
    assert out.max() < -25.0, out.max()


# -------------------------------------------------------------- preamble
def test_channel_estimate_recovers_a_flat_gain(wave):
    cfg, _ = wave
    frame = build_frame(cfg)
    gain = 0.4 * np.exp(1j * 0.7)
    h = channel_estimate(gain * frame.x, frame)
    active = h[np.abs(h) > 1e-9]
    assert np.abs(active).mean() == pytest.approx(np.abs(gain), rel=0.05)


def test_ltf_tones_are_unit_modulus_on_active_subcarriers(wave):
    cfg, _ = wave
    tones = ltf_tones(cfg)
    active = tones[tones != 0]
    assert active.size > 0
    assert np.allclose(np.abs(active), 1.0)
    # apply_cfo is the inverse-able companion of estimate_cfo
    frame = build_frame(cfg)
    rotated = apply_cfo(frame.x, 1e4, cfg.sample_rate_hz)
    assert np.abs(rotated).sum() == pytest.approx(np.abs(frame.x).sum(),
                                                  rel=1e-9)


# -------------------------------------------------------------- plotting
def test_figure_helpers_render_and_write(tmp_path, wave):
    plt = pytest.importorskip("matplotlib.pyplot")
    plt.switch_backend("Agg")
    from wifitrx import plotting

    cfg, wf = wave
    x = wf.x
    y = x * (1 - 0.2 * np.abs(x) ** 2)
    made = {
        "psd.png": lambda p: plotting.plot_psd_comparison(
            {"tx": x, "pa": y}, cfg.sample_rate_hz, path=str(p)),
        "const.png": lambda p: plotting.plot_constellation(
            {"rx": x[:2000]}, path=str(p)),
        "ccdf.png": lambda p: plotting.plot_ccdf({"tx": x}, path=str(p)),
        "amam.png": lambda p: plotting.plot_am_curves(
            {"pa": (x, y)}, path=str(p)),
    }
    for name, build in made.items():
        out = tmp_path / name
        assert build(out) is not None
        assert out.exists() and out.stat().st_size > 1000, name
    plt.close("all")


# ------------------------------------------------------------------- CLI
def test_handoff_cli_inspects_a_cal_state(tmp_path):
    """``python -m wifitrx.handoff inspect`` is the documented way to
    check a delivered bundle (docs/interface_zh.md §3)."""
    import json

    good = tmp_path / "cal_state.json"
    good.write_text(json.dumps({
        "format": "wifitrx-cal-state-v1", "tx": {}, "rx": {},
        "provenance": {"git_commit": "abc", "git_dirty": False},
        "results": [{"name": "tx_iq", "passed": True, "saturated": False,
                     "spec": {"metric": "irr_min_db", "limit": 50.0,
                              "sense": "min"},
                     "metrics_after": {"irr_min_db": 55.0}}]}))
    run = subprocess.run(
        [sys.executable, "-m", "wifitrx.handoff", "inspect", str(good)],
        capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "0 error(s)" in run.stdout, run.stdout

    bad = tmp_path / "broken.json"
    bad.write_text("{not json")
    run = subprocess.run(
        [sys.executable, "-m", "wifitrx.handoff", "inspect", str(bad)],
        capture_output=True, text=True)
    assert run.returncode != 0            # a broken bundle must not pass
