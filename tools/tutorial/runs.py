"""All expensive build-time computation, each executed at most once.

Every number and every result figure in the tutorial comes from here, so
prose can never drift from the code (the sibling-project lesson).  All
seeds fixed; ``--cache`` pickles products for prose iteration only.
"""
from __future__ import annotations

import importlib.util
import pickle
import sys
from dataclasses import replace
from functools import cached_property
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SEED = 5          # the process corner shown throughout the tutorial
BW = 80e6         # fast-config bandwidth for all build-time runs
# tempcos for the temperature chapter (same values the test suite uses)
RC_TEMPCO = 2e-4
IQ_PHASE_TEMPCO = 0.004
LEAK_TEMPCO = 0.02


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RunContext:
    def __init__(self, cache: Path | None = None):
        self._cache_path = cache
        self._cache = {}
        if cache is not None and cache.exists():
            self._cache = pickle.loads(cache.read_bytes())

    def _cached(self, key: str, compute):
        if key in self._cache:
            return self._cache[key]
        value = compute()
        try:
            self._cache[key] = value
            if self._cache_path is not None:
                self._cache_path.write_bytes(pickle.dumps(self._cache))
        except Exception:
            pass
        return value

    # ---------------------------------------------------------- chains
    def _impaired_trx(self, seed: int = SEED, fs: float | None = None):
        """The canonical impaired pair — imported from tests/test_e2e.py
        rather than copied a third time."""
        e2e = _load_module(ROOT / "tests" / "test_e2e.py", "tut_e2e")
        from wifitrx.waveform import OFDMConfig
        cfg = OFDMConfig(bandwidth_hz=BW, qam_order=256, n_symbols=4,
                         oversampling=4)
        tx, rx = e2e.impaired_trx(BW, fs or cfg.sample_rate_hz, seed=seed)
        for p in (tx.params, rx.params):
            p.lpf.rc_tempco_per_c = RC_TEMPCO
            p.iq.phase_tempco_deg_per_c = IQ_PHASE_TEMPCO
        tx.params.lo_leak_tempco_db_per_c = LEAK_TEMPCO
        return tx, rx, cfg

    # ------------------------------------------------------- full cal
    @cached_property
    def full_cal(self) -> dict:
        def compute():
            from wifitrx.cal.sequence import run_full_cal
            from wifitrx.chain import LoopbackPath
            tx, rx, cfg = self._impaired_trx()
            path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
            results = run_full_cal(tx, rx, cfg, path, with_dpd=True,
                                   profile="factory", seed=0)
            by_name = {r.name: r for r in results}
            final = by_name["final_loopback_evm"]

            tx2, rx2, _ = self._impaired_trx()
            res2 = run_full_cal(tx2, rx2, cfg, path, with_dpd=True,
                                profile="poweron", seed=0)
            final2 = {r.name: r for r in res2}["final_loopback_evm"]
            return {
                "results": results, "by_name": by_name,
                "tx": tx, "rx": rx, "cfg": cfg, "path": path,
                "snap_before": final.artifacts["snapshot_before"],
                "snap_after": final.artifacts["snapshot_after"],
                "evm_before": final.metrics_before["evm_db"],
                "evm_after": final.metrics_after["evm_db"],
                "tx_evm_db": final.metrics_after["tx_evm_db"],
                "capture_ms_factory": final.metrics_after["capture_time_ms"],
                "captures_factory": final.metrics_after["total_captures"],
                "capture_ms_poweron": final2.metrics_after["capture_time_ms"],
                "captures_poweron": final2.metrics_after["total_captures"],
                "evm_after_poweron": final2.metrics_after["evm_db"],
                "poweron_results": res2,
            }
        # not routed through _cached: live chain objects (needed by
        # temp_study) don't survive pickling meaningfully
        return compute()

    # ----------------------------------------- single-impairment study
    @cached_property
    def impairment_study(self) -> dict:
        def compute():
            study = _load_module(
                ROOT / "examples" / "run_impairment_study.py", "tut_imp")
            from wifitrx.cal.sync import _fractional_advance, align_delay
            from wifitrx.chain import (LoopbackPath, RxChain, TxChain,
                                       run_loopback)
            from wifitrx.impairments.converters import ADCParams
            from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
            from wifitrx.impairments.phase_noise import LOModel
            from wifitrx.impairments.analog_filter import TunableLPF
            from wifitrx.metrics import aclr, evm
            from wifitrx.units import power_dbm
            from wifitrx.waveform import (OFDMConfig, demodulate_ofdm,
                                          generate_ofdm)

            cfg = OFDMConfig(bandwidth_hz=BW, qam_order=1024, n_symbols=6,
                             oversampling=4)
            fs = cfg.sample_rate_hz
            wf = generate_ofdm(cfg)
            x = wf.x * 0.1
            cases = {
                "clean": (study.clean_tx(BW), study.clean_rx(BW)),
                "tx_iq_imbalance": (replace(study.clean_tx(BW),
                    iq=FreqDepIQImbalance(gain_db=0.3, phase_deg=2.0,
                                          gd_mismatch_ps=200.0,
                                          rail_ripple_db=0.3,
                                          rail_gd_ripple_ns=0.1)),
                    study.clean_rx(BW)),
                "tx_lo_leak": (replace(study.clean_tx(BW),
                                       lo_leak_dbm=-28.0),
                               study.clean_rx(BW)),
                "tx_phase_noise": (replace(study.clean_tx(BW),
                                           lo=LOModel(enabled=True)),
                                   study.clean_rx(BW)),
                "tx_pa_8db_backoff": (replace(study.clean_tx(BW),
                                              pa_enabled=True),
                                      study.clean_rx(BW)),
                "rx_iq_imbalance": (study.clean_tx(BW),
                    replace(study.clean_rx(BW),
                            iq=FreqDepIQImbalance(gain_db=0.3, phase_deg=2.0,
                                                  gd_mismatch_ps=200.0))),
                "rx_dc_offset": (study.clean_tx(BW),
                    replace(study.clean_rx(BW),
                            dc_offset=(0.02 + 0.015j,) * 4)),
                "adc_9bit": (study.clean_tx(BW),
                    replace(study.clean_rx(BW),
                            adc=ADCParams(bits=9, enabled=True))),
                "lpf_corner_-20pct": (replace(study.clean_tx(BW),
                    lpf=TunableLPF(fc_nominal_hz=BW / 2 * 1.1,
                                   rc_error=-0.2)),
                    study.clean_rx(BW)),
            }
            rows, signals = [], {}
            for name, (txp, rxp) in cases.items():
                tx = TxChain(txp, fs)
                rx = RxChain(rxp, fs)
                rx.noise_enabled = False
                rx.agc(power_dbm(tx(x)))
                out = run_loopback(tx, rx, x,
                                   LoopbackPath(atten_db=0.0, delay_ns=0.0))
                _, _, info = align_delay(wf.x, out, max_lag=256)
                out = _fractional_advance(out, info["lag_total"])
                g = np.vdot(wf.x, out) / np.vdot(wf.x, wf.x)
                res = evm(demodulate_ofdm(out / g, wf), wf.tx_symbols,
                          equalize="per_tone")
                try:
                    ac = aclr(out, fs, BW)
                    ac_worst = max(ac["lower_dbc"], ac["upper_dbc"])
                except Exception:
                    ac_worst = float("nan")
                rows.append({"case": name, "evm_db": res.db,
                             "aclr_dbc": ac_worst})
                signals[name] = out
            return {"rows": rows, "signals": signals, "fs": fs, "bw": BW}
        return self._cached("impairment_study", compute)

    # ------------------------------------------------------ studies
    @cached_property
    def temp_study(self) -> dict:
        def compute():
            from wifitrx.link.temp_study import temperature_hold_study
            fc = self.full_cal
            return temperature_hold_study(
                fc["tx"], fc["rx"], fc["path"], fc["cfg"], fc["results"],
                temps=(-40.0, -10.0, 25.0, 55.0, 85.0))
        return self._cached("temp_study", compute)

    @cached_property
    def sensitivity(self) -> list[dict]:
        def compute():
            from wifitrx.chain import RxChain, RxParams
            from wifitrx.link.sensitivity import sensitivity_study
            from wifitrx.waveform import OFDMConfig
            bw = 20e6
            cfg = OFDMConfig(bandwidth_hz=bw, qam_order=64, n_symbols=4,
                             oversampling=2)
            p = RxParams(bandwidth_hz=bw)
            p.lo.enabled = False
            p.lpf.fc_nominal_hz = bw / 2 * 1.3
            rx = RxChain(p, cfg.sample_rate_hz)
            return sensitivity_study(rx, cfg, [0, 5, 9], seed=2)
        return self._cached("sensitivity", compute)

    @cached_property
    def drift_tracking(self) -> dict:
        def compute():
            from wifitrx.cal.dpd_tracking import track_dpd
            from wifitrx.chain import RxChain, RxParams, TxChain, TxParams
            from wifitrx.impairments.analog_filter import TunableLPF
            from wifitrx.impairments.converters import ADCParams, DACParams
            from wifitrx.impairments.iq_imbalance import FreqDepIQImbalance
            from wifitrx.impairments.phase_noise import LOModel
            from wifitrx.pa import DriftingReferencePA, DriftingScaledPA
            from wifitrx.waveform import OFDMConfig, generate_ofdm

            cfg = OFDMConfig(bandwidth_hz=BW, qam_order=256, n_symbols=4,
                             oversampling=4)
            fs = cfg.sample_rate_hz
            wf = generate_ofdm(cfg)
            drift = DriftingReferencePA(drive0=0.13, drive_span=0.02,
                                        beta_a_span=0.15, alpha_p_span=0.5)
            pa = DriftingScaledPA(drift, gain_db=26.0, psat_dbm=28.0)
            tx = TxChain(TxParams(bandwidth_hz=BW,
                                  dac=DACParams(enabled=True),
                                  lpf=TunableLPF(enabled=False),
                                  iq=FreqDepIQImbalance(enabled=False),
                                  lo=LOModel(enabled=False),
                                  pa_enabled=True), fs, pa=pa)
            rx = RxChain(RxParams(bandwidth_hz=BW, nonlin_enabled=False,
                                  iq=FreqDepIQImbalance(enabled=False),
                                  dc_offset=(),
                                  lpf=TunableLPF(enabled=False),
                                  adc=ADCParams(enabled=False),
                                  lo=LOModel(enabled=False)), fs)
            rx.noise_enabled = False
            rx.agc(-20.0)
            res = track_dpd(tx, rx, wf, np.linspace(0.0, 1.0, 10),
                            drive_scale=0.12)
            return {"trace": res.trace, "metrics": res.metrics_after}
        return self._cached("drift_tracking", compute)

    @cached_property
    def mc_yield(self) -> dict:
        """A small illustrative Monte-Carlo (the real gate is
        examples/run_yield.py --runs 20 in the nightly)."""
        def compute():
            from wifitrx.cal.sequence import loopback_evm, run_full_cal
            from wifitrx.chain import LoopbackPath
            evms = []
            for seed in range(1, 7):
                tx, rx, cfg = self._impaired_trx(seed=seed)
                path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
                run_full_cal(tx, rx, cfg, path, with_dpd=False,
                             profile="poweron", seed=0)
                evms.append(loopback_evm(tx, rx, path, cfg,
                                         drive_scale=0.12))
            return {"evms": evms}
        return self._cached("mc_yield", compute)
