"""M4 tests: DPD, AGC sweep, link budget and EVM budget."""
import numpy as np
import pytest

from wifitrx.cal.agc_cal import calibrate_agc
from wifitrx.cal.dpd_cal import calibrate_dpd
from wifitrx.chain import LoopbackPath, RxChain, RxParams, TxChain, TxParams
from wifitrx.impairments.analog_filter import TunableLPF
from wifitrx.impairments.converters import ADCParams, DACParams
from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
from wifitrx.impairments.phase_noise import LOModel
from wifitrx.link import (
    EvmBudget, Stage, adc_equivalent_stage, cascade_iip3_dbm, cascade_nf_db,
    mcs, sensitivity_dbm,
)
from wifitrx.units import KT_DBM_HZ
from wifitrx.waveform import OFDMConfig, generate_ofdm

FS = 320e6
BW = 160e6


def test_dpd_improves_aclr_and_evm():
    cfg = OFDMConfig(bandwidth_hz=80e6, qam_order=256, n_symbols=8,
                     oversampling=4)
    wf = generate_ofdm(cfg)
    fs = cfg.sample_rate_hz
    tx = TxChain(TxParams(bandwidth_hz=80e6, dac=DACParams(enabled=True),
                          lpf=TunableLPF(enabled=False),
                          iq=FreqDepIQImbalance(enabled=False),
                          lo=LOModel(enabled=False), pa_enabled=True), fs)
    rx = RxChain(RxParams(bandwidth_hz=80e6, nonlin_enabled=False,
                          iq=FreqDepIQImbalance(enabled=False), dc_offset=(),
                          lpf=TunableLPF(enabled=False),
                          adc=ADCParams(enabled=False),
                          lo=LOModel(enabled=False)), fs)
    rx.noise_enabled = False
    rx.agc(-20.0)
    # drive_scale=0.25 -> ~18 dBm avg out, 10 dB backoff: visible compression
    res = calibrate_dpd(tx, rx, wf, LoopbackPath(atten_db=40.0, delay_ns=6.0))
    assert res.metrics_after["aclr_worst_dbc"] < \
        res.metrics_before["aclr_worst_dbc"] - 10.0, res.trace
    assert res.metrics_after["evm_db"] < res.metrics_before["evm_db"] - 5.0


def test_agc_sweep_lands_and_snr():
    rx = RxChain(RxParams(bandwidth_hz=BW, nonlin_enabled=True,
                          iq=FreqDepIQImbalance(enabled=False), dc_offset=(),
                          lpf=TunableLPF(fc_nominal_hz=90e6),
                          adc=ADCParams(enabled=True),
                          lo=LOModel(enabled=False)), FS)
    res = calibrate_agc(rx)
    assert res.passed, res.metrics_after


class TestBudget:
    def test_friis_two_stage(self):
        stages = [Stage("lna", 20.0, 2.0, -5.0), Stage("bb", 30.0, 15.0, 20.0)]
        nf = cascade_nf_db(stages)
        # analytic: F = 10^0.2 + (10^1.5-1)/100
        f_ref = 10 ** 0.2 + (10 ** 1.5 - 1) / 100.0
        assert np.isclose(nf, 10 * np.log10(f_ref), atol=1e-6)

    def test_iip3_dominated_by_backend(self):
        stages = [Stage("lna", 20.0, 2.0, 0.0), Stage("bb", 0.0, 15.0, 10.0)]
        iip3 = cascade_iip3_dbm(stages)
        # backend referred to input: 10 - 20 = -10 dBm dominates
        assert -11.0 < iip3 < -9.5

    def test_sensitivity_mcs0_vs_mcs13(self):
        nf = 6.0
        s0 = sensitivity_dbm(nf, 320e6, mcs(0).snr_req_db)
        s13 = sensitivity_dbm(nf, 320e6, mcs(13).snr_req_db)
        assert s13 - s0 == mcs(13).snr_req_db - mcs(0).snr_req_db
        assert -90.0 < s0 < -70.0
        assert s13 < -35.0

    def test_adc_stage_nf_reasonable(self):
        st = adc_equivalent_stage(bits=11, fullscale_dbm=2.0, backoff_db=12.0,
                                  fs_hz=FS, bw_hz=BW)
        assert 0.0 < st.nf_db < 80.0


def test_evm_budget_rss():
    b = EvmBudget(snr_db=45.0, irr_db=52.0, ipn_rad2=(np.deg2rad(0.5)) ** 2,
                  cpe_tracked_fraction=0.5, pa_nmse_db=-45.0, sqnr_db=55.0)
    doc = b.report(measured_evm_db=-40.0)
    assert -45.0 < doc["predicted_evm_db"] < -35.0
    assert abs(doc["delta_db"]) < 5.0


def test_evm_budget_matches_measured_simple_case():
    """Thermal-only chain: budget prediction vs measured EVM within 1.5 dB."""
    from wifitrx.chain import run_loopback
    from wifitrx.metrics import evm
    from wifitrx.waveform import demodulate_ofdm

    cfg = OFDMConfig(bandwidth_hz=BW, qam_order=256, n_symbols=6, oversampling=2)
    wf = generate_ofdm(cfg)
    tx = TxChain(TxParams(bandwidth_hz=BW, dac=DACParams(enabled=False),
                          lpf=TunableLPF(enabled=False),
                          iq=FreqDepIQImbalance(enabled=False),
                          lo=LOModel(enabled=False), pa_enabled=False), FS)
    rx = RxChain(RxParams(bandwidth_hz=BW, nonlin_enabled=False,
                          iq=FreqDepIQImbalance(enabled=False), dc_offset=(),
                          lpf=TunableLPF(enabled=False),
                          adc=ADCParams(enabled=False),
                          lo=LOModel(enabled=False)), FS)
    p_in = -55.0
    x = wf.x * 10 ** ((p_in - 4.0) / 20.0)  # dac fullscale 4 dBm bypass scale
    rx.agc(p_in)
    out = run_loopback(tx, rx, x, LoopbackPath(atten_db=0.0, delay_ns=0.0),
                       seed=3)
    g = np.vdot(wf.x, out) / np.vdot(wf.x, wf.x)
    measured = evm(demodulate_ofdm(out / g, wf), wf.tx_symbols).db

    st = rx.params.lna_states[rx.lna_idx]
    # in-band SNR: signal power over noise density x BW
    snr = p_in - (KT_DBM_HZ + st.nf_db + 10 * np.log10(BW))
    predicted = EvmBudget(snr_db=snr).predicted_evm_db()
    assert abs(measured - predicted) < 1.5, (measured, predicted)
