"""O3 tests: cal time profiles, per-state IQ, bit-true RTL vectors."""
import numpy as np

from wifitrx.cal.rx_iq import calibrate_rx_iq_per_state, measure_rx_irr
from wifitrx.cal.sequence import run_full_cal
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams
from wifitrx.deploy.vectors import (make_dpd_vectors, make_wl_vectors,
                                    save_vectors, verify_vectors)
from wifitrx.impairments.analog_filter import TunableLPF
from wifitrx.impairments.converters import ADCParams, DACParams
from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
from wifitrx.impairments.phase_noise import LOModel
from wifitrx.pa.gmp import GMPModel
from wifitrx.waveform import OFDMConfig


def _trx(bw, fs, seed=5):
    rng = np.random.default_rng(seed)
    txp = TxParams(bandwidth_hz=bw).randomize(rng)
    rxp = RxParams(bandwidth_hz=bw).randomize(rng)
    txp.lpf.fc_nominal_hz = bw / 2 * 1.3
    rxp.lpf.fc_nominal_hz = bw / 2 * 1.12
    return TxChain(txp, fs), RxChain(rxp, fs)


class TestProfiles:
    def test_poweron_much_cheaper_similar_evm(self):
        bw = 80e6
        cfg = OFDMConfig(bandwidth_hz=bw, qam_order=1024, n_symbols=6,
                         oversampling=4)
        fs = cfg.sample_rate_hz
        path = LoopbackPath(atten_db=40.0, delay_ns=6.0)

        def run(profile):
            tx, rx = _trx(bw, fs)
            results = run_full_cal(tx, rx, cfg, path, with_dpd=False,
                                   profile=profile)
            final = {r.name: r for r in results}["final_loopback_evm"]
            return (final.metrics_after["capture_time_ms"],
                    final.metrics_after["evm_db"])

        t_fact, evm_fact = run("factory")
        t_fast, evm_fast = run("poweron")
        assert t_fast < t_fact / 3.0, (t_fast, t_fact)
        assert evm_fast < evm_fact + 2.0, (evm_fast, evm_fact)

    def test_cost_reported_per_step(self):
        bw = 80e6
        cfg = OFDMConfig(bandwidth_hz=bw, qam_order=256, n_symbols=4,
                         oversampling=2)
        tx, rx = _trx(bw, cfg.sample_rate_hz)
        results = run_full_cal(tx, rx, cfg,
                               LoopbackPath(atten_db=40.0, delay_ns=6.0),
                               with_dpd=False)
        with_cost = [r for r in results if r.cost]
        assert len(with_cost) >= 8
        assert all(r.cost["samples"] > 0 for r in with_cost)


class TestPerStateIQ:
    def test_per_state_cal_holds_irr(self):
        bw = 80e6
        fs = bw * 4
        txp = TxParams(bandwidth_hz=bw, dac=DACParams(enabled=False),
                       lpf=TunableLPF(enabled=False),
                       iq=FreqDepIQImbalance(enabled=False), lo_leak_dbm=None,
                       lo=LOModel(enabled=False), pa_enabled=False)
        rxp = RxParams(
            bandwidth_hz=bw, nonlin_enabled=False,
            iq=FreqDepIQImbalance(
                gain_db=0.4, phase_deg=2.0, gd_mismatch_ps=150.0,
                state_phase_step_deg=0.4),   # drifts 0.4 deg per gain state
            dc_offset=(), lpf=TunableLPF(enabled=False),
            adc=ADCParams(enabled=False), lo=LOModel(enabled=False))
        tx = TxChain(txp, fs)
        rx = RxChain(rxp, fs)
        rx.noise_enabled = False

        res = calibrate_rx_iq_per_state(tx, rx,
                                        LoopbackPath(atten_db=30.0,
                                                     delay_ns=6.0))
        assert res.passed, res.metrics_after
        # a single-state w2 would NOT hold across states: check state 3
        # with state-0 correction is visibly worse than its own
        rx.lna_idx = 3
        rx.vga_db = 0.0
        own = res.metrics_after["irr_min_state3"]
        rx.w2_by_state = {3: rx.w2_by_state[0]}
        _, irr_wrong = measure_rx_irr(rx)
        assert float(np.min(irr_wrong)) < own - 5.0


class TestVectors:
    def test_wl_vectors_roundtrip(self, tmp_path):
        rng = np.random.default_rng(0)
        w2 = 0.02 * (rng.standard_normal(31) + 1j * rng.standard_normal(31))
        vec = make_wl_vectors(w2)
        p = save_vectors(vec, tmp_path / "wl_vec.npz")
        assert verify_vectors(p)
        assert (tmp_path / "wl_vec.csv").exists()

    def test_dpd_vectors_roundtrip(self, tmp_path):
        rng = np.random.default_rng(1)
        x = 0.2 * (rng.standard_normal(4096) + 1j * rng.standard_normal(4096))
        def pa_like(u):
            return u - 0.1 * u * np.abs(u) ** 2
        model = GMPModel(order=5, memory_depth=3).fit(x, pa_like(x))
        vec = make_dpd_vectors(model)
        p = save_vectors(vec, tmp_path / "dpd_vec.npz")
        assert verify_vectors(p, dpd_model=model)

    def test_tampered_vectors_fail(self, tmp_path):
        rng = np.random.default_rng(0)
        w2 = 0.02 * (rng.standard_normal(31) + 1j * rng.standard_normal(31))
        vec = make_wl_vectors(w2)
        vec["y_expected"] = vec["y_expected"] + 1e-6
        p = save_vectors(vec, tmp_path / "bad.npz")
        assert not verify_vectors(p)
