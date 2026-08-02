"""N1 tests: memory PA, HB import, drift-tracking DPD."""
import numpy as np
import pytest

from wifitrx.cal.dpd_cal import calibrate_dpd
from wifitrx.cal.dpd_tracking import track_dpd
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams
from wifitrx.impairments.analog_filter import TunableLPF
from wifitrx.impairments.converters import ADCParams, DACParams
from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
from wifitrx.impairments.phase_noise import LOModel
from wifitrx.pa import (DriftingReferencePA, DriftingScaledPA, ScaledPA,
                        WienerHammersteinPA, load_hb_pa)
from wifitrx.waveform import OFDMConfig, generate_ofdm


def _clean_tx(bw, **kw):
    d = dict(bandwidth_hz=bw, dac=DACParams(enabled=True),
             lpf=TunableLPF(enabled=False),
             iq=FreqDepIQImbalance(enabled=False), lo_leak_dbm=None,
             lo=LOModel(enabled=False), pa_enabled=True)
    d.update(kw)
    return TxParams(**d)


def _clean_rx(bw, **kw):
    d = dict(bandwidth_hz=bw, nonlin_enabled=False,
             iq=FreqDepIQImbalance(enabled=False), dc_offset=(),
             lpf=TunableLPF(enabled=False), adc=ADCParams(enabled=False),
             lo=LOModel(enabled=False))
    d.update(kw)
    return d


class TestMemoryPA:
    def test_memory_pa_selection(self):
        fs = 320e6
        tx = TxChain(_clean_tx(80e6, pa_model="memory"), fs)
        from wifitrx.pa.reference_pa import ReferencePA
        assert isinstance(tx.pa.pa_model, ReferencePA)
        # dBm mapping still holds: saturation peak == psat
        p_in = np.linspace(-20.0, 20.0, 1500)
        assert np.isclose(np.max(tx.pa.am_am(p_in)), 28.0, atol=0.2)

    def test_dpd_on_memory_pa(self):
        cfg = OFDMConfig(bandwidth_hz=80e6, qam_order=256, n_symbols=8,
                         oversampling=4)
        fs = cfg.sample_rate_hz
        wf = generate_ofdm(cfg)
        tx = TxChain(_clean_tx(80e6, pa_model="memory"), fs)
        rxp = RxParams(bandwidth_hz=80e6, nonlin_enabled=False,
                       iq=FreqDepIQImbalance(enabled=False), dc_offset=(),
                       lpf=TunableLPF(enabled=False),
                       adc=ADCParams(enabled=False), lo=LOModel(enabled=False))
        rx = RxChain(rxp, fs)
        rx.noise_enabled = False
        res = calibrate_dpd(tx, rx, wf, LoopbackPath(atten_db=40.0, delay_ns=6.0),
                            drive_scale=0.2)
        assert res.metrics_after["aclr_worst_dbc"] < \
            res.metrics_before["aclr_worst_dbc"] - 10.0, res.trace
        assert res.metrics_after["evm_db"] < res.metrics_before["evm_db"] - 5.0


class TestHBImport:
    def test_load_hb_pa_and_scale(self, tmp_path):
        # synthesize an AM-AM table in dBm (what spectre HB sweep exports)
        pin = np.linspace(-30.0, 10.0, 60)
        a_in = np.sqrt(10 ** (pin / 10.0))
        saleh_like = 2.0 * a_in / (1 + 0.8 * a_in ** 2)
        pout = 10 * np.log10(saleh_like ** 2) + 12.0
        phase = 8.0 * (a_in ** 2) / (1 + 3.0 * a_in ** 2)
        csv = tmp_path / "amam.csv"
        rows = ["pin_dbm,pout_dbm,phase_deg"]
        rows += [f"{a:.4f},{b:.4f},{c:.4f}" for a, b, c in zip(pin, pout, phase)]
        csv.write_text("\n".join(rows))

        pa = load_hb_pa(str(csv))
        assert isinstance(pa, WienerHammersteinPA)
        scaled = ScaledPA(pa, gain_db=26.0, psat_dbm=28.0)
        p_in = np.linspace(-25.0, 15.0, 1200)
        p_out = scaled.am_am(p_in)
        assert np.isclose(np.max(p_out), 28.0, atol=0.3)
        assert np.isclose(p_out[0] - p_in[0], 26.0, atol=0.3)


class TestDriftTracking:
    @pytest.mark.slow
    def test_tracking_holds_evm_frozen_degrades(self):
        cfg = OFDMConfig(bandwidth_hz=80e6, qam_order=256, n_symbols=6,
                         oversampling=4)
        fs = cfg.sample_rate_hz
        wf = generate_ofdm(cfg)
        # moderate thermal drift: stays inside the PA's invertible region
        drift = DriftingReferencePA(drive0=0.13, drive_span=0.02,
                                    beta_a_span=0.15, alpha_p_span=0.5)
        pa = DriftingScaledPA(drift, gain_db=26.0, psat_dbm=28.0)
        tx = TxChain(_clean_tx(80e6), fs, pa=pa)
        rxp = RxParams(bandwidth_hz=80e6, nonlin_enabled=False,
                       iq=FreqDepIQImbalance(enabled=False), dc_offset=(),
                       lpf=TunableLPF(enabled=False),
                       adc=ADCParams(enabled=False), lo=LOModel(enabled=False))
        rx = RxChain(rxp, fs)
        rx.noise_enabled = False
        rx.agc(-20.0)

        schedule = np.linspace(0.0, 1.0, 8)
        res = track_dpd(tx, rx, wf, schedule, drive_scale=0.12)
        assert res.passed, res.metrics_after
        # frozen DPD must be visibly worse at the hot end
        tr = res.trace
        assert tr[-1]["evm_frozen_db"] > tr[-1]["evm_track_db"] + 4.0, tr[-1]
