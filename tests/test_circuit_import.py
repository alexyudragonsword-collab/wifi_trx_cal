"""O2 tests: circuit-data importers and full-cal revalidation on templates."""
from pathlib import Path

import numpy as np
import pytest

from wifitrx.circuit_import import fit_lpf_from_ac, load_pll_pn_csv
from wifitrx.impairments.phase_noise import ldbc_from_sphi
from wifitrx.pa import ScaledPA, load_hb_pa

DATA = Path(__file__).resolve().parent.parent / "circuit_data"


class TestPllPn:
    def test_template_loads_and_interpolates(self):
        prof = load_pll_pn_csv(DATA / "pll_pn_6g.csv")
        l_100k = float(ldbc_from_sphi(prof.psd(np.array([1e5])))[0])
        assert -105.0 < l_100k < -99.0
        l_10m = float(ldbc_from_sphi(prof.psd(np.array([1e7])))[0])
        assert l_10m < -130.0

    def test_rejects_garbage(self, tmp_path):
        p = tmp_path / "bad.csv"
        p.write_text("offset_hz,dbchz\n1e4,-999\n1e5,-100\n1e6,-110\n")
        with pytest.raises(ValueError, match="合理范围"):
            load_pll_pn_csv(p)

    def test_rejects_too_few_points(self, tmp_path):
        p = tmp_path / "short.csv"
        p.write_text("offset_hz,dbchz\n1e4,-100\n")
        with pytest.raises(ValueError, match="不足"):
            load_pll_pn_csv(p)

    def test_header_variants_and_comments(self, tmp_path):
        p = tmp_path / "v.csv"
        p.write_text("# spectre pnoise\nFrequency\tPhase Noise\n"
                     "1e4\t-100\n1e5\t-105\n1e6\t-120\n")
        prof = load_pll_pn_csv(p)
        assert len(prof.f_pts) == 3


class TestLpfAc:
    def test_template_fit(self):
        lpf, info = fit_lpf_from_ac(DATA / "lpf_ac_tx.csv",
                                    fc_nominal_hz=208e6)
        # template synthesized with +9% corner shift, butter5
        assert abs(info["rc_error"] - 0.09) < 0.02, info
        assert info["order"] == 5
        assert abs(lpf.fc_actual_hz / (208e6 * 1.09) - 1) < 0.03

    def test_corner_unreachable_rejected(self, tmp_path):
        p = tmp_path / "flat.csv"
        rows = ["freq_hz,mag_db"] + [f"{f:.0f},0.0"
                                     for f in np.linspace(1e6, 1e8, 20)]
        p.write_text("\n".join(rows))
        with pytest.raises(ValueError, match="-3 dB"):
            fit_lpf_from_ac(p, fc_nominal_hz=208e6)


class TestPaTemplate:
    def test_template_scales(self):
        pa = load_hb_pa(str(DATA / "pa_hb_amam.csv"))
        scaled = ScaledPA(pa, gain_db=26.0, psat_dbm=28.0)
        p_in = np.linspace(-25.0, 15.0, 1200)
        p_out = scaled.am_am(p_in)
        assert np.isclose(np.max(p_out), 28.0, atol=0.3)
        assert 20.0 < scaled.p1db_out_dbm < 27.5


@pytest.mark.slow
def test_full_cal_on_circuit_templates():
    """The whole sequence still converges with imported circuit data."""
    from wifitrx.cal.sequence import run_full_cal
    from wifitrx.chain import (LoopbackPath, RxChain, RxParams, TxChain,
                               TxParams)
    from wifitrx.impairments.phase_noise import LOModel
    from wifitrx.waveform import OFDMConfig

    bw = 320e6
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=1024, n_symbols=4,
                     oversampling=4)
    fs = cfg.sample_rate_hz
    prof = load_pll_pn_csv(DATA / "pll_pn_6g.csv")
    tx_lpf, _ = fit_lpf_from_ac(DATA / "lpf_ac_tx.csv",
                                fc_nominal_hz=bw / 2 * 1.3)
    pa = ScaledPA(load_hb_pa(str(DATA / "pa_hb_amam.csv")),
                  gain_db=26.0, psat_dbm=28.0)
    rng = np.random.default_rng(5)
    txp = TxParams(bandwidth_hz=bw).randomize(rng)
    rxp = RxParams(bandwidth_hz=bw).randomize(rng)
    txp.lpf = tx_lpf
    txp.lo = LOModel(freq_hz=6.0e9, profile=prof)
    rxp.lo = LOModel(freq_hz=6.0e9, profile=prof)
    rxp.lpf.fc_nominal_hz = bw / 2 * 1.12
    tx = TxChain(txp, fs, pa=pa)
    rx = RxChain(rxp, fs)
    # path=None -> the bandwidth-dependent cal-coupler design point
    # (34 dB at 320 MHz: the state-2 observation with real NF 22 needs
    # the hotter input; 40 dB here starves rx_iq of observation SNR)
    results = run_full_cal(tx, rx, cfg)
    final = {r.name: r for r in results}["final_loopback_evm"]
    assert final.metrics_after["tx_evm_db"] < -37.0, final.metrics_after
    for r in results:
        assert r.passed in (True, None), (r.name, r.metrics_after)
