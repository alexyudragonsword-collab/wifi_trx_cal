"""Regenerate the on-device golden values (androidTest/assets/golden.json).

Run on the desktop after any change that legitimately moves delivered
numbers (and say so in CHANGELOG):

    python android/tools/make_golden.py

The instrumented test replays the same three analyses on-device through
the same bridge and compares metric-by-metric: numeric within 0.05 dB
absolute or 1e-3 relative (BLAS/FFT implementations differ — bit
identity is not the claim), everything else exact.  Three cases cover the
three compute classes: full calibration sequence, RX sweep with isolation
splits, and the pure-arithmetic spur planner.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "android" / "app" / "src" / "main" / "python"))

CASES = [
    ("full_cal", {"bw_mhz": 80, "qam": 256, "seed": 5, "with_dpd": False,
                  "std": "11ax/be", "rx_hp": False, "baseband": False,
                  "agc_rebw": False, "bb_noise_nv": 5}),
    ("rx_evm_sweep", {"bw_mhz": 80, "qam": 256, "seed": 5,
                      "std": "11ax/be", "rx_hp": False, "baseband": False,
                      "agc_rebw": False, "bb_noise_nv": 5}),
    ("spur_planner", {"bw_mhz": 320, "band": "6g"}),
]


def main() -> None:
    import bridge
    golden = []
    for key, params in CASES:
        out = json.loads(bridge.run(key, json.dumps(params)))
        assert out["ok"], f"{key}: {out.get('error')}"
        golden.append({"key": key, "params": params,
                       "metrics": out["metrics"],
                       "n_pages": len(out["pages"])})
        print(f"{key}: {len(out['metrics'])} metrics, "
              f"{len(out['pages'])} page(s)")
    # beside bridge.py, i.e. inside the Chaquopy source dir: the golden
    # values ship in the APK so the app can self-check on the device it
    # is actually installed on (the emulator job only covers x86_64).
    dst = (REPO / "android" / "app" / "src" / "main" / "python"
           / "golden.json")
    dst.write_text(json.dumps(golden, indent=1))
    print("wrote", dst)


if __name__ == "__main__":
    main()
