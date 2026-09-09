# wifitrx calibration state: handoff

This directory's `cal_state.json` is the deliverable: every digital correction plus the analog tuning codes, the per-step verdicts against the acceptance specs in force when they ran, and the residual figures a link simulation consumes.

format `wifitrx-cal-state-v1` · 40 MHz · 256-QAM · fs 160 MS/s

## How to consume it

```bash
python -m wifitrx.handoff inspect cal_state.json   # verdicts, stdlib-only
python -m wifitrx.handoff replay  cal_state.json   # residuals applied literally vs the file's own EVM
```

To restore this exact part in the model:

```python
from wifitrx.cal.base import load_cal_state
tx_state, rx_state = load_cal_state('cal_state.json')
tx.load_correction_state(tx_state)
rx.load_correction_state(rx_state)
# analog tuning codes travel with the params: rerun the two
# cheap corner searches (see wifitrx.handoff.runner)
```

## Measurement conditions

Everything below changes the numbers; a consumer who cannot state these cannot reproduce them.

* `adc_backoff_db` = 12.0
* `bandwidth_hz` = 40000000.0
* `ce_smooth_tones` = 9
* `n_symbols` = 6
* `oversampling` = 4
* `qam_order` = 256
* `rx_lpf_family` = butter
* `rx_lpf_order` = 5
* `shared_lo_loopback` = True
* `subcarrier_spacing_hz` = 78125.0
* `tx_lpf_family` = butter
* `tx_lpf_order` = 5
* `waveform_seed` = 0
* `with_dpd` = True

## Steps

| # | step | passed | trim railed | spec |
|---|---|---|---|---|
| 1 | `tx_lpf_corner` | yes | no | fc_err_pct abs_max 2.0 |
| 2 | `rx_lpf_corner` | yes | no | fc_err_pct abs_max 2.0 |
| 3 | `rx_dc_offset` | yes | — | worst_dc_dbfs max -50.0 |
| 4 | `tx_lo_leak_envdet` | yes | — | lo_leak_dbc max -40.0 |
| 5 | `tx_lo_leak_loopback` | yes | — | lo_leak_dbc max -40.0 |
| 6 | `rx_iip2` | yes | no | iip2_dbm min 55.0 |
| 7 | `loopback_delay` | yes | — | — |
| 8 | `tx_iq` | yes | — | irr_min_db min 50.0 |
| 9 | `group_delay` | yes | — | error_ps abs_max 80.0 |
| 10 | `rx_iq` | yes | — | irr_min_db min 50.0 |
| 11 | `tx_power` | yes | — | — |
| 12 | `dpd` | yes | — | — |
| 13 | `agc_sweep` | yes | — | worst_landing_err_db max 2.5 |
| 14 | `final_loopback_evm` | yes | — | tx_evm_modem_db max -38.0 |

## Two EVM views

Every EVM figure in this file is reported twice from the same capture. `*_evm_db` is the **isolation view**: per-tone LS equalisation against the ideal reference plus genie common-phase removal — only the chain's impairments, which is why the residual replay closes on it. `*_evm_modem_db` is the **modem form**: LTF CFO acquisition, the LTF channel estimate smoothed over `ce_smooth_tones` adjacent tones and frozen for the packet, then pilot-only common-phase removal — what a standard receiver reads, and the figure the spec verdict is taken on (`fc_err_pct abs_max 2.0`, `fc_err_pct abs_max 2.0`, `worst_dc_dbfs max -50.0`, `lo_leak_dbc max -40.0`, `lo_leak_dbc max -40.0`, `iip2_dbm min 55.0`, `irr_min_db min 50.0`, `error_ps abs_max 80.0`, `irr_min_db min 50.0`, `worst_landing_err_db max 2.5`, `tx_evm_modem_db max -38.0`). The gap between the two is the receiver's own estimation loss, not a residual of the chain; do not inject either.

* `tx_evm_db` = -41.99 dB
* `tx_evm_modem_db` = -41.64 dB
* `rx_evm_db` = -41.79 dB
* `rx_evm_modem_db` = -41.8 dB

## Residuals

Each figure ships with its own specification in the JSON (`residuals.specification`): unit, meaning, whether larger or smaller is better, and **the recipe for injecting it into a link simulation** (`apply`). Read that rather than inferring from the names — an image-rejection figure applied as a gain imbalance does not give the same constellation as the same dB applied as a quadrature error. `role` says how each key is meant to be consumed: `impairment` entries are injectable, `figure` and `condition` entries are context, `total` entries are measured wholes and must never be re-injected.

| key | value | unit | better | role |
|---|---|---|---|---|
| `agc_sweep.min_snr_db_above_-50dBm` | 32.77 | dB | larger | figure |
| `agc_sweep.worst_landing_err_db` | 0.2252 | dB | smaller magnitude | figure |
| `dpd.aclr_worst_dbc` | -41.75 | dBc | more negative | figure |
| `dpd.evm_db` | -41.93 | dB | more negative | impairment |
| `final_loopback_evm.evm_db` | -42.37 | dB | more negative | total |
| `final_loopback_evm.evm_modem_db` | -42.52 | dB | more negative | total |
| `final_loopback_evm.rx_evm_db` | -41.79 | dB | more negative | total |
| `final_loopback_evm.rx_evm_modem_db` | -41.8 | dB | more negative | total |
| `final_loopback_evm.rx_gain_state` | 3 | index | n/a | condition |
| `final_loopback_evm.rx_im3_dbc` | -53.95 | dBc | more negative | impairment |
| `final_loopback_evm.rx_input_dbm` | -28.53 | dBm | n/a — an operating point, not a defect | condition |
| `final_loopback_evm.rx_nf_db` | 18.67 | dB | smaller | impairment |
| `final_loopback_evm.rx_phase_err_dbc` | -42.99 | dBc | more negative | impairment |
| `final_loopback_evm.tx_evm_db` | -41.99 | dB | more negative | total |
| `final_loopback_evm.tx_evm_modem_db` | -41.64 | dB | more negative | total |
| `group_delay.error_ps` | -18.06 | ps | smaller magnitude | impairment |
| `group_delay.estimated_ps` | 31.24 | ps | n/a — an estimate of the part, not a defect left in | figure |
| `loopback_delay.delay_ns` | 49.29 | ns | n/a — a property of the test path, not of the part | condition |
| `rx_dc_offset.worst_dc_dbfs` | -72.41 | dBFS | more negative | impairment |
| `rx_dc_offset.worst_dc_dbfs_after_analog` | -34.03 | dBFS | more negative | figure |
| `rx_iip2.iip2_dbm` | 74.5 | dBm | larger | impairment |
| `rx_iq.irr_min_db` | 59.19 | dB | larger | impairment |
| `rx_lpf_corner.fc_err_pct` | -0.4356 | % | smaller magnitude | figure |
| `rx_lpf_corner.fc_hz` | 2.23e+07 | Hz | n/a — a design target, not a defect | impairment |
| `tx_iq.irr_min_db` | 52.95 | dB | larger | impairment |
| `tx_lo_leak_envdet.lo_leak_dbc` | -65.6 | dBc | more negative | impairment |
| `tx_lo_leak_loopback.lo_leak_dbc` | -68.14 | dBc | more negative | impairment |
| `tx_lpf_corner.fc_err_pct` | -0.6834 | % | smaller magnitude | figure |
| `tx_lpf_corner.fc_hz` | 2.582e+07 | Hz | n/a — a design target, not a defect | impairment |

Pairs describing one physical quantity measured two ways — apply at most one of each:

* `tx_lo_leak_envdet.lo_leak_dbc` / `tx_lo_leak_loopback.lo_leak_dbc` (keep the second)

