"""Multi-chain (MIMO) transceiver: N TX/RX chains + coupling + LO skew.

Architecture assumptions (2x2 default, structure scales to 4x4):

* one shared synthesizer; the LO distribution tree adds a per-chain phase
  offset (``lo_skew_deg``) and timing skew (``lo_skew_ps``) — the
  quantities the inter-chain alignment calibration must remove for
  beamforming;
* inter-chain coupling: each PA output leaks into every other chain's
  observation/receive path with ``coupling_db`` attenuation (flat model);
* the calibration coupler network can route ANY TX to ANY RX
  (``loopback_capture(i, j)``), which the alignment cal exploits by using
  one RX as the common phase reference.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..units import db_to_amp
from .loopback import LoopbackPath, frac_delay
from .params import RxParams, TxParams
from .rx import RxChain
from .tx import TxChain


@dataclass
class MimoParams:
    n_chains: int = 2
    coupling_db: float = -25.0
    coupling_phase_deg: float = 60.0   # phase of the inter-chain leak
    lo_skew_deg: tuple = (0.0, 12.0)
    lo_skew_ps: tuple = (0.0, 180.0)
    seed: int = 0

    def __post_init__(self):
        # pad the skew tuples if fewer entries than chains were given
        if len(self.lo_skew_deg) < self.n_chains:
            self.lo_skew_deg = tuple(self.lo_skew_deg) + (0.0,) * (
                self.n_chains - len(self.lo_skew_deg))
        if len(self.lo_skew_ps) < self.n_chains:
            self.lo_skew_ps = tuple(self.lo_skew_ps) + (0.0,) * (
                self.n_chains - len(self.lo_skew_ps))

    def randomize(self, rng: np.random.Generator) -> "MimoParams":
        return MimoParams(
            n_chains=self.n_chains,
            coupling_db=self.coupling_db,
            lo_skew_deg=tuple(
                [0.0] + [float(rng.uniform(-25.0, 25.0))
                         for _ in range(self.n_chains - 1)]),
            lo_skew_ps=tuple(
                [0.0] + [float(rng.uniform(-300.0, 300.0))
                         for _ in range(self.n_chains - 1)]),
            seed=int(rng.integers(0, 2 ** 31)),
        )


class MimoTrx:
    def __init__(self, params: MimoParams, fs: float,
                 tx_params: list[TxParams] | None = None,
                 rx_params: list[RxParams] | None = None,
                 bandwidth_hz: float = 160e6, seed: int = 0):
        self.params = params
        self.fs = float(fs)
        rng = np.random.default_rng(seed)
        n = params.n_chains
        if tx_params is None:
            tx_params = [TxParams(bandwidth_hz=bandwidth_hz).randomize(rng)
                         for _ in range(n)]
        if rx_params is None:
            rx_params = [RxParams(bandwidth_hz=bandwidth_hz).randomize(rng)
                         for _ in range(n)]
        self.txs = [TxChain(p, fs) for p in tx_params]
        self.rxs = [RxChain(p, fs) for p in rx_params]
        self.precoder: np.ndarray | None = None  # digital decoupling matrix

    # ------------------------------------------------------------ pieces
    def _skew(self, i: int, y: np.ndarray) -> np.ndarray:
        """Apply chain i's LO-distribution phase and timing skew."""
        ph = np.deg2rad(self.params.lo_skew_deg[i])
        y = y * np.exp(1j * ph)
        tau = self.params.lo_skew_ps[i] * 1e-12 * self.fs
        if tau:
            y = frac_delay(y, tau)
        return y

    def tx(self, i: int, x: np.ndarray, **kw) -> np.ndarray:
        """Chain i PA output including its LO-distribution skew."""
        return self._skew(i, self.txs[i](x, **kw))

    def coupling_matrix_true(self) -> np.ndarray:
        """Ground-truth port coupling matrix (diag 1, off-diag the leak)."""
        n = self.params.n_chains
        c = db_to_amp(self.params.coupling_db) * np.exp(
            1j * np.deg2rad(self.params.coupling_phase_deg))
        m = np.full((n, n), c, dtype=complex)
        np.fill_diagonal(m, 1.0)
        return m

    def tx_all(self, x_mat: np.ndarray) -> np.ndarray:
        """(n_chains, n) digital in -> (n_chains, n) PA-port outputs
        including inter-chain coupling.  A programmed ``precoder`` (from
        the decoupling cal) is applied to the digital streams first."""
        x_mat = np.asarray(x_mat, dtype=complex)
        if self.precoder is not None:
            x_mat = self.precoder @ x_mat
        outs = np.stack([self.tx(i, x_mat[i])
                         for i in range(self.params.n_chains)])
        return self.coupling_matrix_true() @ outs

    def port_capture(self, j_port: int, x_mat: np.ndarray,
                     path: LoopbackPath | None = None,
                     seed: int = 0) -> np.ndarray:
        """Observe antenna port j (all chains transmitting, coupling
        included) through the cal coupler into the common reference RX_0."""
        if path is None:
            path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
        rng = np.random.default_rng(seed)
        y = self.tx_all(x_mat)[j_port]
        y = path.apply(y, self.fs)
        return self.rxs[0](y, rng=rng)

    def loopback_capture(self, i_tx: int, j_rx: int, x: np.ndarray,
                         path: LoopbackPath | None = None,
                         seed: int = 0) -> np.ndarray:
        """Cal-coupler capture TX_i -> RX_j (other chains idle)."""
        if path is None:
            path = LoopbackPath(atten_db=40.0, delay_ns=6.0)
        rng = np.random.default_rng(seed)
        n = np.asarray(x).size
        tx, rx = self.txs[i_tx], self.rxs[j_rx]
        phi = tx.lo_phase(n, rng) if tx.params.lo.enabled else None
        y = self._skew(i_tx, tx(x, phi_lo=phi))
        y = path.apply(y, self.fs)
        return rx(y, phi_lo=phi, rng=rng)
