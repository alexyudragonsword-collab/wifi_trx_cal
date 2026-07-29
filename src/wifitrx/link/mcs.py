"""802.11be MCS table: modulation, coding rate, required SNR, TX EVM limit.

Required SNR values are AWGN approximations (uncoded-to-coded engineering
numbers commonly used for budgeting, not simulated capacity limits); TX EVM
limits follow IEEE 802.11be Draft (Table "Allowed relative constellation
error"): -38 dB for 4096-QAM (MCS12/13).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mcs:
    index: int
    modulation: str
    bits_per_symbol: int
    coding_rate: str
    snr_req_db: float       # approximate required SNR (AWGN)
    tx_evm_limit_db: float  # standard TX EVM requirement


MCS_TABLE = (
    Mcs(0, "BPSK", 1, "1/2", 2.0, -5.0),
    Mcs(1, "QPSK", 2, "1/2", 5.0, -10.0),
    Mcs(2, "QPSK", 2, "3/4", 8.0, -13.0),
    Mcs(3, "16-QAM", 4, "1/2", 11.0, -16.0),
    Mcs(4, "16-QAM", 4, "3/4", 14.5, -19.0),
    Mcs(5, "64-QAM", 6, "2/3", 18.5, -22.0),
    Mcs(6, "64-QAM", 6, "3/4", 20.5, -25.0),
    Mcs(7, "64-QAM", 6, "5/6", 22.5, -27.0),
    Mcs(8, "256-QAM", 8, "3/4", 26.5, -30.0),
    Mcs(9, "256-QAM", 8, "5/6", 28.5, -32.0),
    Mcs(10, "1024-QAM", 10, "3/4", 32.5, -35.0),
    Mcs(11, "1024-QAM", 10, "5/6", 34.5, -35.0),
    Mcs(12, "4096-QAM", 12, "3/4", 38.0, -38.0),
    Mcs(13, "4096-QAM", 12, "5/6", 40.0, -38.0),
)


def mcs(index: int) -> Mcs:
    return MCS_TABLE[index]


def qam_order_for(m: Mcs) -> int:
    return 2 ** m.bits_per_symbol
