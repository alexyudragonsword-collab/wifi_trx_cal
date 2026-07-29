"""M0 smoke tests: vendored OFDM/QAM round-trip integrity."""
import numpy as np
import pytest

from wifitrx.waveform import (
    OFDMConfig, generate_ofdm, demodulate_ofdm,
    qam_constellation, qam_modulate, qam_demodulate,
)
from wifitrx.metrics import evm


@pytest.mark.parametrize("order", [4, 64, 1024, 4096])
def test_qam_roundtrip(order):
    rng = np.random.default_rng(0)
    symbols = rng.integers(0, order, size=1000)
    points = qam_modulate(symbols, order)
    assert np.allclose(np.mean(np.abs(points) ** 2), 1.0, atol=0.1)
    back = qam_demodulate(points, order)
    np.testing.assert_array_equal(back, symbols)


def test_qam_constellation_unit_power():
    for order in (16, 256, 4096):
        c = qam_constellation(order)
        assert c.size == order
        assert np.isclose(np.mean(np.abs(c) ** 2), 1.0)


@pytest.mark.parametrize("bw,qam", [(20e6, 64), (80e6, 1024)])
def test_ofdm_roundtrip_clean(bw, qam):
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=qam, n_symbols=4, oversampling=2)
    wf = generate_ofdm(cfg)
    rx = demodulate_ofdm(wf.x, wf)
    res = evm(rx, wf.tx_symbols, equalize="scalar")
    assert res.db < -60.0


def test_ofdm_320mhz_4096qam():
    cfg = OFDMConfig(bandwidth_hz=320e6, qam_order=4096, n_symbols=2, oversampling=2)
    wf = generate_ofdm(cfg)
    assert cfg.n_active == 3984
    assert cfg.sample_rate_hz == 640e6
    rx = demodulate_ofdm(wf.x, wf)
    res = evm(rx, wf.tx_symbols, equalize="scalar")
    assert res.db < -60.0
