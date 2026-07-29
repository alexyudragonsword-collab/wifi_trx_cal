# Vendored from PA_DPD:src/padpd/dpd/adaptive.py (internal sibling repo), adapted for wifitrx.
# Upstream changes should be ported manually; see PROVENANCE.md.
"""Adaptive / online DPD over a linear-in-parameters basis.

Batch ILA (:class:`~padpd.dpd.ila.ILAPredistorter`) identifies the
predistorter once. A shipped product instead adapts continuously from a
TX->coupler->RX loopback so the DPD tracks PA drift (temperature,
supply, aging). Because GMP/DDR/MP are linear in their coefficients, the
indirect-learning update reduces to a recursive linear estimator on the
post-inverse regressors:

    drive PA with u = DPD(x);  observe y;  target G in y ~= G*x
    post-inverse regressors  Phi = basis(y / G),   target = u
    reduce  || u - Phi @ w ||  and apply  DPD(x) = basis(x) @ w

The ``|x|^k`` polynomial columns make the regressor covariance
ill-conditioned (condition number ~1e10), so a plain gradient method
(LMS/NLMS) either diverges or stalls -- the same reason batch fitting
uses closed-form least squares rather than SGD. Every method offered here
therefore uses the *off-diagonal* covariance to clear that conditioning;
they differ in how much of it they use per step, trading cost for speed:

- ``"rls"`` (default): exponentially-weighted recursive least squares in
  block covariance form, ``R = ff*R + Phi^H Phi``, ``p = ff*p + Phi^H u``,
  solved as ``w = (R + ridge*I)^{-1} p`` each block. O(N^2)/block, reaches
  the least-squares floor in ~1 block, most robust. ``forget`` (ff) sets
  the tracking memory (smaller = faster, noisier).
- ``"whitened"``: a one-time Cholesky whitening (O(N^3)) of the first
  block's covariance, then NLMS in the decorrelated domain. Applying the
  dense whitening is O(N^2)/sample -- the *same per-sample order as
  block-RLS*, not cheaper; what it buys is per-sample tracking and it can
  settle very low on stationary data. The whitening is frozen from block
  0, so it goes stale if the *signal* statistics change (waveform /
  bandwidth / power) -- RLS re-estimates the covariance every block and is
  the more robust default.
- ``"apa"``: affine projection -- decorrelate over the last ``apa_k``
  regressor rows (a mini-RLS window), O(apa_k^2 * N)/sample. ``apa_k=1``
  is NLMS, larger approaches RLS: the middle ground that actually *lowers*
  per-sample cost (small ``apa_k``) versus RLS/whitened.

Plain LMS/NLMS and naive *diagonal* preconditioning are intentionally
*not* offered: on this basis the instability comes from column
correlation (off-diagonal covariance), not scale, so scale-only methods
still diverge (see ``scripts/run_lms_vs_rls.py``).
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from ..pa.base import PAModel
from ..pa.gmp import GMPModel

_METHODS = ("rls", "apa", "whitened")


class AdaptiveDPD:
    def __init__(self, model_factory: Callable[[], PAModel] | None = None,
                 target_gain: complex | None = None,
                 forget: float = 0.995, ridge: float = 1e-6,
                 method: str = "rls", mu: float = 0.5, apa_k: int = 4,
                 apa_delta: float = 1e-3, whiten_ridge: float = 1e-3):
        if method not in _METHODS:
            raise ValueError(
                f"method must be one of {_METHODS}; plain LMS/NLMS and "
                "diagonal preconditioning diverge on the ill-conditioned "
                "polynomial DPD basis (see module docstring)")
        self.template = (model_factory or GMPModel)()
        if not hasattr(self.template, "basis_matrix"):
            raise TypeError("adaptive DPD needs a linear-in-params model "
                            "with basis_matrix() (GMP/DDR/MP)")
        self.method = method
        self.target_gain = target_gain
        self.forget = float(forget)
        self.ridge = float(ridge)
        self.mu = float(mu)
        self.apa_k = int(apa_k)
        self.apa_delta = float(apa_delta)
        self.whiten_ridge = float(whiten_ridge)
        self.w: np.ndarray | None = None
        self._R: np.ndarray | None = None   # RLS covariance
        self._p: np.ndarray | None = None   # RLS cross term
        self._wf: np.ndarray | None = None   # whitening transform (once)
        self._v: np.ndarray | None = None    # whitened-domain weights

    @property
    def n_coeffs(self) -> int:
        return self.template.n_coeffs

    def _phi(self, x: np.ndarray) -> np.ndarray:
        return self.template.basis_matrix(x)

    def _init(self, n: int) -> None:
        if self.w is None:
            self.w = np.zeros(n, dtype=complex)
            self.w[0] = 1.0                      # start from pass-through
            self._R = np.zeros((n, n), dtype=complex)
            self._p = np.zeros(n, dtype=complex)

    def predistort(self, x: np.ndarray) -> np.ndarray:
        if self.w is None:
            return np.asarray(x, dtype=complex)
        return self._phi(x) @ self.w

    __call__ = predistort

    # ---- per-method coefficient update ------------------------------
    def _update_rls(self, phi: np.ndarray, u: np.ndarray) -> None:
        self._R = self.forget * self._R + phi.conj().T @ phi
        self._p = self.forget * self._p + phi.conj().T @ u
        n = self._R.shape[0]
        lam = self.ridge * np.trace(self._R).real / max(n, 1)
        self.w = np.linalg.solve(self._R + lam * np.eye(n), self._p)

    def _update_apa(self, phi: np.ndarray, u: np.ndarray) -> None:
        k = self.apa_k
        eye_k = self.apa_delta * np.eye(k)
        for n in range(k, phi.shape[0]):
            p = phi[n - k:n]                        # k x N window
            e = u[n - k:n] - p @ self.w
            gram = p @ p.conj().T + eye_k
            self.w = self.w + self.mu * p.conj().T @ np.linalg.solve(gram, e)

    def _update_whitened(self, phi: np.ndarray, u: np.ndarray) -> None:
        n = phi.shape[1]
        if self._wf is None:
            r = phi.conj().T @ phi / phi.shape[0]
            lam = self.whiten_ridge * np.trace(r).real / max(n, 1)
            chol = np.linalg.cholesky(r + lam * np.eye(n))
            self._wf = np.linalg.inv(chol.conj().T)   # cov(phi @ wf) ~ I
            self._v = chol.conj().T @ self.w          # w = wf @ v
        z = phi @ self._wf
        v = self._v
        for k in range(z.shape[0]):
            zk = z[k]
            e = u[k] - zk @ v
            v = v + self.mu * np.conj(zk) * e / (np.vdot(zk, zk).real + 1e-6)
        self._v = v
        self.w = self._wf @ v

    def update(self, pa: Callable[[np.ndarray], np.ndarray],
               x: np.ndarray) -> dict:
        """Run one adaptation block against ``pa``; returns block metrics.

        ``pa`` may change between calls (a drifting PA) — that is the
        point. Returns ``{"resid_db", "gain_db", "coeff_norm"}`` where
        ``resid_db`` is the post-inverse fit residual (a proxy for how
        well the DPD currently matches the PA).
        """
        u = self.predistort(x)
        y = pa(u)
        if self.target_gain is None:
            self.target_gain = complex(np.vdot(x, y) / np.vdot(x, x))
        phi = self._phi(y / self.target_gain)
        self._init(phi.shape[1])

        if self.method == "rls":
            self._update_rls(phi, u)
        elif self.method == "apa":
            self._update_apa(phi, u)
        else:
            self._update_whitened(phi, u)

        resid = u - phi @ self.w
        return {
            "resid_db": 10 * np.log10(
                float(np.mean(np.abs(resid) ** 2)
                      / (np.mean(np.abs(u) ** 2) + 1e-30)) + 1e-30),
            "gain_db": 20 * np.log10(abs(self.target_gain) + 1e-30),
            "coeff_norm": float(np.linalg.norm(self.w)),
        }

    def warm_start(self, pa: Callable[[np.ndarray], np.ndarray],
                   x: np.ndarray, blocks: int = 3) -> dict:
        """Converge from pass-through with a few blocks on a static PA."""
        info = {}
        for _ in range(blocks):
            info = self.update(pa, x)
        return info

    def as_model(self) -> PAModel:
        """Freeze the current coefficients into a plain PAModel."""
        m = type(self.template)(**self.template.get_config())
        m.coeffs = None if self.w is None else self.w.copy()
        return m

    def save(self, path: str) -> None:
        if self.w is None:
            raise RuntimeError("nothing to save; run update() first")
        np.savez(path, class_name=type(self.template).__name__,
                 config=repr(self.template.get_config()), coeffs=self.w,
                 target_gain=np.complex128(self.target_gain),
                 method=self.method)
