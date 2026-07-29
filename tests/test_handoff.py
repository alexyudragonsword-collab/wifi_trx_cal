"""O1 tests: handoff waveform format, runner scenarios, batch regression."""
import numpy as np
import pytest

from wifitrx.handoff import (Waveform, build_calibrated_trx, load_waveform,
                             run_handoff, run_regression, save_waveform,
                             validate_waveform)
from wifitrx.waveform import OFDMConfig, generate_ofdm

BW = 80e6
FS = BW * 4


def _wave(scale="digital_fs", rms=0.12, n_symbols=4):
    cfg = OFDMConfig(bandwidth_hz=BW, qam_order=256, n_symbols=n_symbols,
                     oversampling=int(FS / BW))
    wf = generate_ofdm(cfg)
    return Waveform(iq=wf.x * rms, fs_hz=FS, bandwidth_hz=BW, scale=scale,
                    description="test wave")


class TestWaveformIO:
    def test_roundtrip(self, tmp_path):
        w = _wave()
        p = save_waveform(tmp_path / "w.npz", w)
        w2 = load_waveform(p)
        np.testing.assert_allclose(w2.iq, w.iq)
        assert w2.fs_hz == FS and w2.bandwidth_hz == BW
        assert w2.scale == "digital_fs"
        assert not validate_waveform(w2)

    @pytest.mark.parametrize("mutate,frag", [
        (lambda w: setattr(w, "iq", w.iq.real.astype(float)), "复数"),
        (lambda w: setattr(w, "iq", w.iq[:100]), "样本数过少"),
        (lambda w: setattr(w, "scale", "volts"), "scale"),
        (lambda w: setattr(w, "fs_hz", BW * 1.5), "欠采样"),
        (lambda w: setattr(w, "fs_hz", BW * 2.3), "整数倍"),
        (lambda w: setattr(w, "iq", w.iq * 20.0), "满量程"),
        (lambda w: setattr(w, "iq",
                           np.where(np.arange(w.iq.size) == 5, np.nan, w.iq)),
         "NaN"),
    ])
    def test_validation_rejects(self, mutate, frag):
        w = _wave()
        mutate(w)
        issues = validate_waveform(w)
        assert any(frag in s for s in issues), issues

    def test_load_rejects_foreign_npz(self, tmp_path):
        np.savez(tmp_path / "x.npz", data=np.zeros(4))
        with pytest.raises(ValueError, match="wifitrx-wave"):
            load_waveform(tmp_path / "x.npz")


@pytest.fixture(scope="module")
def trx():
    return build_calibrated_trx(BW, FS, seed=5)


class TestRunner:

    def test_loopback_scenario(self, trx):
        tx, rx = trx
        res = run_handoff(_wave(), tx, rx, scenario="loopback")
        assert res.output.scale == "digital_fs"
        assert "pa_out_dbm" in res.metrics
        assert "composite_gain_db" in res.metrics
        assert "aclr_worst_dbc" in res.metrics

    def test_tx_only_scenario(self, trx):
        tx, rx = trx
        res = run_handoff(_wave(), tx, rx, scenario="tx_only")
        assert res.output.scale == "sqrt_mw"
        assert 0.0 < res.metrics["pa_avg_pae"] < 0.35

    def test_rx_only_scenario(self, trx):
        tx, rx = trx
        w = _wave(scale="sqrt_mw", rms=1.0)
        w.iq = w.iq / np.sqrt(np.mean(np.abs(w.iq) ** 2)) * 10 ** (-50 / 20.0)
        res = run_handoff(w, tx, rx, scenario="rx_only")
        assert res.output.scale == "digital_fs"
        assert np.isclose(res.metrics["rx_in_dbm"], -50.0, atol=0.5)

    def test_bad_wave_rejected(self, trx):
        tx, rx = trx
        w = _wave()
        w.fs_hz = BW * 2.3
        with pytest.raises(ValueError, match="校验未通过"):
            run_handoff(w, tx, rx)

    def test_fs_mismatch_rejected(self, trx):
        tx, rx = trx
        w = _wave()
        w.fs_hz = FS * 2
        w.bandwidth_hz = BW * 2
        with pytest.raises(ValueError, match="采样率"):
            run_handoff(w, tx, rx)


def test_regression_report(tmp_path):
    waves = tmp_path / "waves"
    waves.mkdir()
    for i in range(2):
        save_waveform(waves / f"case{i}.npz", _wave())
    np.savez(waves / "broken.npz", data=np.zeros(4))  # foreign file -> row noted
    tx, rx = build_calibrated_trx(BW, FS, seed=5)
    report = run_regression(waves, tx, rx, tmp_path / "out")
    text = report.read_text(encoding="utf-8")
    assert "case0.npz" in text and "case1.npz" in text
    assert "通信侧 EVM" in text
    assert (tmp_path / "out" / "case0_out.npz").exists()
