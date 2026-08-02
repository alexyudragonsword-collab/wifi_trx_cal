"""M1 tests: TX/RX chains, loopback and dBm bookkeeping."""
import numpy as np

from wifitrx.chain import (
    LoopbackPath, RxChain, RxParams, TxChain, TxParams, run_loopback,
)
from wifitrx.impairments.analog_filter import TunableLPF
from wifitrx.impairments.converters import ADCParams, DACParams
from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
from wifitrx.impairments.phase_noise import LOModel
from wifitrx.units import KT_DBM_HZ, power_dbm
from wifitrx.waveform import OFDMConfig, generate_ofdm, demodulate_ofdm
from wifitrx.metrics import evm

FS = 320e6  # 160 MHz BW x2 oversampling for fast tests


def clean_tx_params(**kw):
    d = dict(
        bandwidth_hz=160e6,
        dac=DACParams(enabled=False),
        lpf=TunableLPF(enabled=False),
        iq=FreqDepIQImbalance(enabled=False),
        lo_leak_dbm=None,
        lo=LOModel(enabled=False),
        pa_enabled=False,
    )
    d.update(kw)
    return TxParams(**d)


def clean_rx_params(**kw):
    d = dict(
        bandwidth_hz=160e6,
        nonlin_enabled=False,
        iq=FreqDepIQImbalance(enabled=False),
        dc_offset=(),
        lpf=TunableLPF(enabled=False),
        adc=ADCParams(enabled=False),
        lo=LOModel(enabled=False),
    )
    d.update(kw)
    return RxParams(**d)


def _ofdm(n_symbols=4, bw=160e6, qam=256):
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=qam, n_symbols=n_symbols,
                     oversampling=2)
    return generate_ofdm(cfg)


class TestBypassIdentity:
    def test_loopback_is_scaled_identity(self):
        wf = _ofdm()
        tx = TxChain(clean_tx_params(), FS)
        rx = RxChain(clean_rx_params(), FS)
        rx.noise_enabled = False
        rx.vga_db = 0.0
        path = LoopbackPath(atten_db=0.0, delay_ns=0.0)
        out = run_loopback(tx, rx, wf.x * 0.1, path)
        # overall gain: dac_fs * lna(36 dB default state 0) / adc_fs
        g = np.vdot(wf.x, out) / np.vdot(wf.x, wf.x)
        res = evm(demodulate_ofdm(out / g, wf), wf.tx_symbols)
        assert res.db < -55.0


class TestBookkeeping:
    def test_tx_node_powers(self):
        wf = _ofdm()
        p = TxParams(
            bandwidth_hz=160e6,
            dac=DACParams(bits=12, fullscale_dbm=4.0),
            lpf=TunableLPF(fc_nominal_hz=90e6),
            vga_gain_db=0.0,
            iq=FreqDepIQImbalance(enabled=False),
            lo=LOModel(enabled=False),
            pa_gain_db=26.0, psat_dbm=28.0,
        )
        tx = TxChain(p, FS)
        nodes = {}
        # drive at 12 dB digital backoff from DAC FS
        x = wf.x / np.sqrt(np.mean(np.abs(wf.x) ** 2)) * 10 ** (-12 / 20)
        tx(x, nodes=nodes)
        assert np.isclose(nodes["dac_out_dbm"], 4.0 - 12.0, atol=0.3)
        # PA output ~ bb - lpf loss + 26, well below psat
        assert nodes["pa_out_dbm"] < 28.0
        assert 0.03 < nodes["pa_avg_pae"] < 0.35

    def test_rx_noise_floor_matches_nf(self):
        n = 1 << 16
        rx = RxChain(clean_rx_params(), FS)
        rx.vga_db = 0.0
        out = rx(np.zeros(n, dtype=complex), rng=np.random.default_rng(0))
        st = rx.params.lna_states[rx.lna_idx]
        # digital-domain power reads analog dBm minus the ADC full-scale
        expected_dbm = (KT_DBM_HZ + st.nf_db + 10 * np.log10(FS) + st.gain_db
                        - rx.params.adc.fullscale_dbm)
        assert np.isclose(power_dbm(out), expected_dbm, atol=0.5)


class TestAGC:
    def test_agc_lands_on_target(self):
        rx = RxChain(clean_rx_params(), FS)
        rx.noise_enabled = False
        for p_in in (-70.0, -50.0, -30.0, -10.0):
            rx.agc(p_in)
            st = rx.params.lna_states[rx.lna_idx]
            landed = p_in + st.gain_db + rx.vga_db
            target = rx.params.adc.fullscale_dbm - rx.params.adc_backoff_db
            assert abs(landed - target) < 2.0

    def test_agc_picks_lower_gain_for_big_signals(self):
        rx = RxChain(clean_rx_params(), FS)
        rx.agc(-70.0)
        hi = rx.lna_idx
        rx.agc(-15.0)
        lo = rx.lna_idx
        assert lo > hi


class TestImpairedLoopback:
    def test_impairments_degrade_evm(self):
        wf = _ofdm(n_symbols=4)
        rng = np.random.default_rng(7)
        txp = clean_tx_params().randomize(rng)
        txp = txp  # randomized impairments on
        tx = TxChain(txp, FS)
        rx = RxChain(clean_rx_params(), FS)
        rx.noise_enabled = False
        rx.vga_db = 0.0
        path = LoopbackPath(atten_db=0.0, delay_ns=0.0)
        out = run_loopback(tx, rx, wf.x * 0.1, path)
        g = np.vdot(wf.x, out) / np.vdot(wf.x, wf.x)
        res = evm(demodulate_ofdm(out / g, wf), wf.tx_symbols)
        # sizeable degradation vs the clean case
        assert res.db > -45.0

    def test_shared_lo_cancels_phase_noise(self):
        wf = _ofdm(n_symbols=2)
        txp = clean_tx_params(lo=LOModel(enabled=True))
        rxp = clean_rx_params(lo=LOModel(enabled=True))
        path = LoopbackPath(atten_db=0.0, delay_ns=0.0)

        def run(shared):
            tx = TxChain(txp, FS)
            rx = RxChain(rxp, FS)
            rx.noise_enabled = False
            rx.vga_db = 0.0
            out = run_loopback(tx, rx, wf.x * 0.1, path, shared_lo=shared)
            g = np.vdot(wf.x, out) / np.vdot(wf.x, wf.x)
            return evm(demodulate_ofdm(out / g, wf), wf.tx_symbols).db

        evm_shared = run(True)
        evm_indep = run(False)
        assert evm_shared < evm_indep - 10.0  # correlated PN cancels
