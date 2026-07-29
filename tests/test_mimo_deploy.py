"""N4 tests: MIMO 2x2 chains, inter-chain alignment, fixed-point export."""
import numpy as np
import pytest

from wifitrx.cal.mimo_align import calibrate_mimo_align
from wifitrx.cal.sequence import run_full_cal, tx_evm
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams
from wifitrx.chain.mimo import MimoParams, MimoTrx
from wifitrx.deploy import (export_c_header, export_coeff_csv,
                            quantization_sweep, select_min_bits,
                            quantize_symmetric)
from wifitrx.impairments.analog_filter import TunableLPF
from wifitrx.impairments.converters import ADCParams, DACParams
from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
from wifitrx.impairments.phase_noise import LOModel
from wifitrx.waveform import OFDMConfig

FS = 320e6
BW = 80e6


def _clean_txp():
    return TxParams(bandwidth_hz=BW, dac=DACParams(enabled=False),
                    lpf=TunableLPF(enabled=False),
                    iq=FreqDepIQImbalance(enabled=False), lo_leak_dbm=None,
                    lo=LOModel(enabled=False), pa_enabled=False)


def _clean_rxp():
    return RxParams(bandwidth_hz=BW, nonlin_enabled=False,
                    iq=FreqDepIQImbalance(enabled=False), dc_offset=(),
                    lpf=TunableLPF(enabled=False), adc=ADCParams(enabled=False),
                    lo=LOModel(enabled=False))


class TestMimoAlign:
    @pytest.mark.parametrize("seed", range(3))
    def test_alignment_residuals(self, seed):
        rng = np.random.default_rng(seed)
        mp = MimoParams(n_chains=2).randomize(rng)
        mimo = MimoTrx(mp, FS, tx_params=[_clean_txp(), _clean_txp()],
                       rx_params=[_clean_rxp(), _clean_rxp()])
        for rx in mimo.rxs:
            rx.noise_enabled = False
        res = calibrate_mimo_align(mimo)
        assert res.passed, res.metrics_after
        # the injected skew must have been visible before the cal
        assert (abs(res.metrics_before["chain1_phase_deg"]) > 2.0
                or abs(res.metrics_before["chain1_delay_ps"]) > 50.0)

    def test_coupling_appears_in_tx_all(self):
        mp = MimoParams(n_chains=2, coupling_db=-25.0,
                        lo_skew_deg=(0.0, 0.0), lo_skew_ps=(0.0, 0.0))
        mimo = MimoTrx(mp, FS, tx_params=[_clean_txp(), _clean_txp()],
                       rx_params=[_clean_rxp(), _clean_rxp()])
        n = 4096
        x = np.zeros((2, n), dtype=complex)
        t = np.arange(n) / FS
        x[0] = 0.1 * np.exp(2j * np.pi * 11e6 * t)
        outs = mimo.tx_all(x)
        p0 = np.mean(np.abs(outs[0]) ** 2)
        p1 = np.mean(np.abs(outs[1]) ** 2)
        assert np.isclose(10 * np.log10(p1 / p0), -25.0, atol=0.5)


class TestFixedPoint:
    def _calibrated_tx(self):
        cfg = OFDMConfig(bandwidth_hz=BW, qam_order=256, n_symbols=4,
                         oversampling=4)
        fs = cfg.sample_rate_hz
        rng = np.random.default_rng(7)
        txp = TxParams(bandwidth_hz=BW).randomize(rng)
        rxp = RxParams(bandwidth_hz=BW).randomize(rng)
        txp.lpf.fc_nominal_hz = BW / 2 * 1.3
        rxp.lpf.fc_nominal_hz = BW / 2 * 1.12
        tx = TxChain(txp, fs)
        rx = RxChain(rxp, fs)
        run_full_cal(tx, rx, cfg, LoopbackPath(atten_db=40.0, delay_ns=6.0),
                     with_dpd=False)
        return tx, cfg

    def test_quantization_sweep_and_selection(self):
        tx, cfg = self._calibrated_tx()
        w2_float = tx.w2.copy()

        def apply_and_measure(sets):
            tx.w2 = np.asarray(sets["tx_w2"], dtype=complex)
            return tx_evm(tx, cfg, drive_scale=0.12)

        sweep = quantization_sweep({"tx_w2": w2_float}, apply_and_measure,
                                   bit_widths=(6, 8, 10, 12, 14, 16))
        bits = select_min_bits(sweep, max_loss_db=0.5)
        assert bits <= 12, sweep
        row = {r["bits"]: r["metric_db"] for r in sweep["rows"]}
        assert row[12] <= sweep["reference_db"] + 0.5
        # float coefficients restored
        np.testing.assert_allclose(tx.w2, w2_float)

    def test_export_roundtrip(self, tmp_path):
        rng = np.random.default_rng(0)
        coeffs = {"tx_w2": (rng.standard_normal(31) + 1j *
                            rng.standard_normal(31)) * 0.01}
        h = export_c_header(coeffs, tmp_path / "cal_coeffs.h", bits=12)
        text = h.read_text()
        assert "tx_w2[31]" in text and "#ifndef" in text
        c = export_coeff_csv(coeffs, tmp_path / "cal_coeffs.csv", bits=12)
        rows = c.read_text().strip().splitlines()
        assert rows[0] == "set,index,re,im"
        assert len(rows) == 1 + 31
        # CSV values equal the quantized coefficients
        q = quantize_symmetric(coeffs["tx_w2"], 12)
        got = np.array([complex(float(r.split(",")[2]), float(r.split(",")[3]))
                        for r in rows[1:]])
        np.testing.assert_allclose(got, q, rtol=1e-9)
