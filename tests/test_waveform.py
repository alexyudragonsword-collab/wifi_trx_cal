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


# ------------------------------------------------ pilots per numerology
@pytest.mark.parametrize("scs, cp, expected", [
    (78.125e3, 1 / 16, {20e6: 8, 40e6: 16, 80e6: 16, 160e6: 32, 320e6: 64}),
    (312.5e3, 1 / 4, {20e6: 4, 40e6: 6, 80e6: 8, 160e6: 16}),
])
def test_pilot_count_follows_the_numerology(scs, cp, expected):
    """802.11ax Table 27-21 RU pilot sets (8/16/16/32/64) for the
    78.125 kHz numerology, the 802.11a/n/ac sets (4/6/8/16) for 312.5
    kHz.  Until 0.7.17 the legacy table served both — 6 pilots at 40 MHz
    11ax where the standard has 16 — so every pilot-tracked reading
    under-counted the 11ax/be pilots.  Positions are mirror-symmetric,
    inside the active block, and the outermost pilot keeps the
    standard's lever arm (rank-mapped, within 5 % of the band edge)."""
    from wifitrx.waveform.pilots import pilot_positions, standard_pilot_tones

    for bw, n_p in expected.items():
        cfg = OFDMConfig(bandwidth_hz=bw, subcarrier_spacing_hz=scs,
                         cp_fraction=cp, n_symbols=2)
        cols = pilot_positions(cfg)
        tones = cfg.active_tone_indices()[cols]
        assert cols.size == n_p, (bw, cols.size)
        assert np.array_equal(tones, -tones[::-1])
        assert np.unique(cols).size == n_p
        std = standard_pilot_tones(cfg)
        half = cfg.n_active // 2
        assert tones.max() <= half
        assert tones.max() >= std.max() - 0.05 * half, (bw, tones.max(), std.max())
        # the rank map moves a pilot by at most the null tones inside it
        assert np.abs(tones - std).max() <= 44


def test_pilot_table_refuses_to_guess():
    """No silent '8 evenly spaced tones' for a bandwidth or numerology the
    tables do not define — the old fallback hid exactly the kind of
    mismatch this file now pins."""
    from wifitrx.waveform.pilots import pilot_positions

    with pytest.raises(ValueError, match="pilot set"):
        pilot_positions(OFDMConfig(bandwidth_hz=100e6, n_symbols=2))
    with pytest.raises(ValueError, match="pilot set"):
        pilot_positions(OFDMConfig(bandwidth_hz=320e6, subcarrier_spacing_hz=312.5e3,
                                   cp_fraction=1 / 4, n_symbols=2))
    with pytest.raises(ValueError, match="subcarrier spacing"):
        pilot_positions(OFDMConfig(bandwidth_hz=20e6, subcarrier_spacing_hz=156.25e3,
                                   n_symbols=2))
