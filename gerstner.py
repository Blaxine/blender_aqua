# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared Gerstner wave math.

The geometry-nodes ocean tree and the Python buoy handler MUST agree on
these formulas and constants (TDD §6.1.4 / R1.5).  This module is the
single source of truth: the node builder bakes the same per-layer
constant factors symbolically; the handler evaluates them numerically.
"""

import math
from functools import lru_cache

G = 9.81                 # scene gravity magnitude
AMP_DECAY = 0.65         # A_i = Amplitude * AMP_DECAY**i
WL_FALLOFF = 0.62        # lambda_i = Wavelength * WL_FALLOFF**i
N_LAYERS = 5
TWO_PI = 2.0 * math.pi

# Fixed deterministic per-layer direction offsets (radians, scaled by the
# user 'Spread' input).  Table is frozen: changing it is a WAVE_TABLE_TAG bump.
DIR_OFFSETS = (0.0, 0.31, -0.47, 0.83, -0.71, 1.13, -1.02, 0.56)


def layer_params(amplitude, wavelength, direction_deg, spread, speed_mult,
                 choppiness, n=N_LAYERS):
    """Derive per-layer (A, k, omega, cos_th, sin_th, QA) tuples."""
    layers = []
    n = max(1, min(int(n), len(DIR_OFFSETS)))
    for i in range(n):
        amp = amplitude * (AMP_DECAY ** i)
        wl = max(wavelength * (WL_FALLOFF ** i), 1e-4)
        k = TWO_PI / wl
        omega = math.sqrt(G * k) * speed_mult
        theta = math.radians(direction_deg) + DIR_OFFSETS[i] * spread
        # Steepness clamp: Q_i*A_i = min(Choppiness / (k_i * N), A_i)
        qa = min(choppiness / (k * n), amp) if choppiness > 0 else 0.0
        layers.append((amp, k, omega, math.cos(theta), math.sin(theta), qa))
    return layers


def height(layers, x, y, t):
    """Vertical Gerstner displacement at (x, y, t).

    Note: this is the height of the wave field sampled at rest position
    (x, y); the horizontal Gerstner pinch is ignored for buoy sampling,
    which is an accepted approximation (error << amplitude at the
    default choppiness).
    """
    h = 0.0
    for amp, k, omega, cx, sy, _qa in layers:
        h += amp * math.sin(k * (x * cx + y * sy) - omega * t)
    return h


# Stateless FIR smoothing (R1.5): a weighted window over ANALYTIC past
# samples.  Pure function of (x, y, t) -> reproducible at any isolated
# frame, in any order, on any machine.
_FIR_K = 4
_FIR_W = tuple(math.exp(-2.0 * (j / (_FIR_K - 1)) ** 2) for j in range(_FIR_K))
_FIR_NORM = sum(_FIR_W)


@lru_cache(maxsize=256)
def _filtered_layers(layers, smoothing):
    """Exact FIR response as amplitude/phase; bounded, value-keyed cache."""
    dt = smoothing / _FIR_K
    result = []
    for amp, k, omega, cx, sy, _qa in layers:
        real = sum(w * math.cos(omega * j * dt) for j, w in enumerate(_FIR_W)) / _FIR_NORM
        imag = sum(w * math.sin(omega * j * dt) for j, w in enumerate(_FIR_W)) / _FIR_NORM
        result.append((amp * math.hypot(real, imag), k, omega, cx, sy, math.atan2(imag, real)))
    return tuple(result)


def smoothed_height(layers, x, y, t, smoothing):
    if smoothing <= 1e-6:
        return height(layers, x, y, t)
    return sum(amp * math.sin(k * (x * cx + y * sy) - omega * t + phase)
               for amp, k, omega, cx, sy, phase in _filtered_layers(tuple(layers), smoothing))
