"""M5 tests: report generation and determinism."""

from wifitrx.cal.sequence import loopback_evm, run_full_cal
from wifitrx.chain import LoopbackPath
from wifitrx.report.generator import generate_report
from wifitrx.waveform import OFDMConfig

from test_e2e import impaired_trx


def test_report_generation(tmp_path):
    bw = 80e6
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=256, n_symbols=4,
                     oversampling=2)
    fs = cfg.sample_rate_hz
    tx, rx = impaired_trx(bw, fs, seed=3)
    path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
    results = run_full_cal(tx, rx, cfg, path, with_dpd=False)
    report = generate_report(results, tmp_path)
    text = report.read_text(encoding="utf-8")
    assert "校准结果汇总" in text
    for r in results:
        assert r.name in text
    pngs = list((tmp_path / "figs").glob("*.png"))
    assert len(pngs) >= 5


def test_determinism():
    bw = 80e6
    cfg = OFDMConfig(bandwidth_hz=bw, qam_order=256, n_symbols=4,
                     oversampling=2)
    fs = cfg.sample_rate_hz
    path = LoopbackPath(atten_db=40.0, delay_ns=6.0)

    def run():
        tx, rx = impaired_trx(bw, fs, seed=11)
        run_full_cal(tx, rx, cfg, path, with_dpd=False)
        return loopback_evm(tx, rx, path, cfg, seed=2)

    assert run() == run()
