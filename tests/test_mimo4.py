"""O4 tests: 4x4 decoupling and beamforming array-gain validation."""
import numpy as np
import pytest

from wifitrx.cal.mimo_align import (calibrate_mimo_align,
                                    calibrate_mimo_decouple,
                                    measure_coupling_matrix)
from wifitrx.chain.mimo import MimoParams, MimoTrx
from wifitrx.impairments.analog_filter import TunableLPF
from wifitrx.impairments.converters import ADCParams, DACParams
from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
from wifitrx.impairments.phase_noise import LOModel
from wifitrx.chain import RxParams, TxParams
from wifitrx.link.beamforming import array_gain_db, beamforming_study

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


def make_mimo(seed=3, n_chains=4, big_skew=False):
    rng = np.random.default_rng(seed)
    mp = MimoParams(n_chains=n_chains).randomize(rng)
    if big_skew:
        # worst-case LO distribution tree (long routing, corner mismatch):
        # phase errors this large visibly eat beamforming gain
        mp = MimoParams(n_chains=n_chains,
                        lo_skew_deg=(0.0, 45.0, -50.0, 30.0)[:n_chains],
                        lo_skew_ps=(0.0, 250.0, -280.0, 200.0)[:n_chains])
    mimo = MimoTrx(mp, FS, tx_params=[_clean_txp() for _ in range(n_chains)],
                   rx_params=[_clean_rxp() for _ in range(n_chains)])
    for rx in mimo.rxs:
        rx.noise_enabled = False
    return mimo


class TestDecoupling:
    def test_measured_matrix_matches_truth(self):
        mimo = make_mimo()
        calibrate_mimo_align(mimo)
        c = measure_coupling_matrix(mimo)
        truth = mimo.coupling_matrix_true()
        err = np.max(np.abs(c - truth))
        assert err < 0.01, (c, truth)

    def test_decoupling_residual(self):
        mimo = make_mimo()
        calibrate_mimo_align(mimo)
        res = calibrate_mimo_decouple(mimo)
        assert res.metrics_before["worst_crosstalk_db"] > -30.0
        assert res.passed, res.metrics_after


class TestBeamforming:
    @pytest.mark.slow
    def test_array_gain_recovery(self):
        study = beamforming_study(lambda: make_mimo(seed=7, big_skew=True))
        ideal = study["ideal_db"]          # 12.04 dB for 4 chains
        assert study["unaligned_db"] < ideal - 0.6
        assert study["aligned_db"] > study["unaligned_db"]
        assert abs(study["aligned_decoupled_db"] - ideal) < 0.5, study

    def test_array_gain_2x2_sanity(self):
        mimo = make_mimo(seed=1, n_chains=2)
        calibrate_mimo_align(mimo)
        calibrate_mimo_decouple(mimo)
        g = array_gain_db(mimo)
        assert abs(g - 20 * np.log10(2)) < 0.5, g
