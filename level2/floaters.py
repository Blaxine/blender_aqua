# SPDX-License-Identifier: GPL-3.0-or-later
"""Floating objects for the Mantaflow liquid modes: the physics.

Mantaflow has no two-way rigid coupling: effectors push water, water never
pushes objects.  So AquaSuite computes buoyancy itself, frame by frame, from
the baked liquid surface, and writes the motion as keyframes:

* weight m·g, with m = density × mesh volume (closed meshes only);
* buoyancy ρ_water·g·V_sub, summed over sample points inside the object, so
  the offset between the centre of buoyancy and the centre of mass turns the
  object; the force follows the local surface slope (Froude–Krylov), so
  floaters slide down wave faces;
* linear + quadratic water drag on every submerged point, relative to the
  liquid mesh's speed vectors when the bake has them (angular drag follows);
* added mass (a share of the displaced water) so light objects don't jitter;
* floor and wall contacts against the domain's inner bounds;
* in waves of known length (Ocean (Simulated)), the wave's push decays with
  depth below the still water level, as wave pressure does (Smith effect).

The water level comes from a ring of vertical probes just outside the
object, fitted with a plane.  A floater that "pushes water" (a Fluid
effector, two-pass or coupled bake) leaves a hole in the liquid mesh, so
probing under it would find the hull, not the water line.

Two drivers:
* ``bake`` — one-way: read an already-baked domain frame by frame.
* ``CoupledBake`` — two-way: runs inside a blocking Mantaflow bake.  At each
  new frame, ``frame_change_pre`` reads the mesh the solver has just written
  for the previous frame and moves the floaters before the solver sees them
  (their effectors then push the water).

The scene collection, per-object settings and buttons are in
``core/floating.py``.
"""

import gzip
import json
import math
import os
import struct
import time

import bpy
import bmesh
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

from .. import constants as C

RHO_WATER = 1000.0
GRAVITY = 9.81
# kg/m^3.  Water is 1000: below floats, above sinks.
DENSITY_PRESETS = {key: rho for key, _label, rho in C.FLOAT_MATERIALS}
RESTORE_PROP = "aqs_floater_restore"     # JSON pre-bake transform
PREV_ACTION_PROP = "aqs_floater_prev_action"
EFFECTOR_PROP = "aqs_floater_effector"   # "Pushes water" effector we added

DEFAULTS = dict(
    substeps=8,
    drag_linear=5.0,       # 1/s per submerged volume (heave damping)
    drag_quadratic=0.5,    # ~ half a drag coefficient
    added_mass=0.5,        # share of the displaced water carried along
    restitution=0.2,
    friction=0.5,
    layers=10,             # sample layers across the smallest dimension
    max_points=1500,
    ring_points=12,
    ring_gap_cells=2.0,    # probe this many cells outside the footprint
    use_water_velocity=True,
    wave_number=0.0,       # k of the waves (1/m); 0 = no decay with depth
    rest_level=0.0,        # still water level the decay is measured from
)


# ---------------------------------------------------------------------------
# The body: mass, sample points, inertia
# ---------------------------------------------------------------------------

def _scaled_bmesh(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(Matrix.Diagonal(obj.matrix_basis.to_scale()).to_4x4())
    return bm


def is_closed(obj):
    """Every edge borders exactly two faces (no holes, no fins)."""
    if obj.type != "MESH" or not obj.data.polygons:
        return False
    users = {}
    for poly in obj.data.polygons:
        for ek in poly.edge_keys:
            users[ek] = users.get(ek, 0) + 1
    return all(n == 2 for n in users.values())


def mesh_volume(obj):
    """Volume in m^3 with the object's scale (closed meshes only)."""
    bm = _scaled_bmesh(obj)
    try:
        return abs(bm.calc_volume(signed=True))
    finally:
        bm.free()


def eligible(obj):
    """(ok, reason)."""
    if obj.type != "MESH":
        return False, "not a mesh"
    if obj.parent is not None:
        return False, "it has a parent"
    if C.OWNER_PROP in obj.keys() or C.SRC_PROP in obj.keys():
        return False, "it is part of an AquaSuite setup"
    if not is_closed(obj):
        return False, "the mesh has holes (its volume is undefined)"
    return True, ""


def object_settings(obj):
    """(density, mass or None) from the object's Floating Objects settings."""
    s = getattr(obj, "aqs_float", None)
    if s is None:
        return 600.0, None
    return s.density, (s.mass if s.use_mass else None)


class Body:
    """A rigid floater: settings, sample points, inertia and state."""

    def __init__(self, obj, density=None, mass=None, params=None):
        self.obj = obj
        self.p = dict(DEFAULTS, **(params or {}))
        own_density, own_mass = object_settings(obj)
        density = density if density is not None else own_density
        mass = mass if mass is not None else own_mass
        self.volume = mesh_volume(obj)
        self.mass = float(mass) if mass else density * self.volume
        self.density = self.mass / max(self.volume, 1e-9)
        self._sample()
        self.reset()

    def _sample(self):
        bm = _scaled_bmesh(self.obj)
        try:
            bmesh.ops.triangulate(bm, faces=bm.faces[:])
            tree = BVHTree.FromBMesh(bm)
            verts = np.array([v.co[:] for v in bm.verts])
        finally:
            bm.free()
        lo, hi = verts.min(0), verts.max(0)
        size = hi - lo
        spacing = max(min(size) / self.p["layers"],
                      (np.prod(size) / self.p["max_points"]) ** (1 / 3))
        n = np.maximum(np.ceil(size / spacing).astype(int), 1)
        xs = [lo[i] + (np.arange(n[i]) + 0.5) * size[i] / n[i] for i in range(3)]
        pts = []
        # A column of points is inside between successive crossings of a
        # vertical ray (closed mesh: enter, leave, enter, ...).
        for x in xs[0]:
            for y in xs[1]:
                hits, z = [], lo[2] - 1.0
                for _ in range(64):
                    loc, _nrm, _i, _d = tree.ray_cast(Vector((x, y, z)), Vector((0, 0, 1)))
                    if loc is None:
                        break
                    hits.append(loc.z)
                    z = loc.z + 1e-6
                for a, b in zip(hits[0::2], hits[1::2]):
                    pts.extend((x, y, zz) for zz in xs[2] if a <= zz <= b)
        pts = np.array(pts) if pts else ((lo + hi) / 2)[None, :]
        self.layer = float(size[2] / n[2])
        self.com_local = pts.mean(0)
        self.points = pts - self.com_local
        self.dv = self.volume / len(pts)
        dm = self.mass / len(pts)
        r2 = (self.points ** 2).sum(1)
        cell = (size / n) ** 2
        self.inertia = dm * (np.eye(3) * r2.sum() - self.points.T @ self.points)
        self.inertia += np.diag([cell[1] + cell[2], cell[0] + cell[2], cell[0] + cell[1]]) \
            * dm * len(pts) / 12.0
        self.inertia_inv = np.linalg.inv(self.inertia)
        hull = verts - self.com_local
        if len(hull) > 400:
            hull = hull[np.linspace(0, len(hull) - 1, 400).astype(int)]
        self.hull = hull
        self.reach = float(np.sqrt((self.points[:, :2] ** 2).sum(1)).max() + spacing / 2)
        self.length = self.volume ** (1 / 3)

    def reset(self):
        from .still_water import world_matrix
        mw = world_matrix(self.obj)
        loc, rot, _sca = mw.decompose()
        self.q = np.array(rot.normalized()[:])            # w, x, y, z
        self.x = np.array((loc + rot.to_matrix() @ Vector(self.com_local))[:])
        self.v = np.zeros(3)
        self.w = np.zeros(3)
        self.vsub = 0.0
        self.track = []

    def rotation(self):
        return np.array(Quaternion(self.q).to_matrix())

    def pose(self):
        """(location, quaternion) of the OBJECT (its origin, not its COM)."""
        R = self.rotation()
        return self.x - R @ self.com_local, self.q.copy()

    def footprint(self):
        """Horizontal radius of the rotated object around its COM."""
        hull = self.hull @ self.rotation().T
        return float(np.sqrt((hull[:, :2] ** 2).sum(1)).max())


def buoy_offset(obj, density):
    """Plane Ocean's analytic buoys are massless: they put the object's
    origin at the water height + Buoyancy Offset.  Floating level at rest,
    a closed mesh of this density sinks until it displaces its own mass:
    returns that offset (origin above the waterline, m), or None when it
    sinks (density >= water)."""
    if density >= RHO_WATER:
        return None
    body = Body(obj, density=density)
    R = np.array(body.obj.matrix_basis.to_quaternion().to_matrix())
    z = body.points @ R.T
    target = density / RHO_WATER * len(z)
    lo, hi = z[:, 2].min() - body.layer, z[:, 2].max() + body.layer
    for _ in range(50):
        mid = (lo + hi) / 2
        sub = np.clip((mid - z[:, 2]) / body.layer + 0.5, 0.0, 1.0).sum()
        lo, hi = (mid, hi) if sub < target else (lo, mid)
    waterline = (lo + hi) / 2 + body.com_local @ R.T @ np.array((0, 0, 1.0))
    return float(-waterline)


# ---------------------------------------------------------------------------
# The liquid surface around the floaters
# ---------------------------------------------------------------------------

class Surface:
    """One frame of liquid mesh (world space) near the floaters."""

    def __init__(self, verts, tris, vel=None, regions=None):
        self.n_verts = len(verts)
        if regions:
            cen = verts[tris].mean(1)
            keep = np.zeros(len(tris), bool)
            for (x0, y0, x1, y1) in regions:
                keep |= (cen[:, 0] >= x0) & (cen[:, 0] <= x1) \
                    & (cen[:, 1] >= y0) & (cen[:, 1] <= y1)
            tris = tris[keep]
        used, inv = np.unique(tris, return_inverse=True)
        self.verts = verts[used]
        self.tris = inv.reshape(-1, 3)
        self.vel = vel[used] if vel is not None else None
        self.tree = BVHTree.FromPolygons(self.verts.tolist(), self.tris.tolist()) \
            if len(self.tris) else None

    @classmethod
    def from_domain(cls, dom, depsgraph, regions=None):
        ev = dom.evaluated_get(depsgraph)
        me = ev.to_mesh()
        try:
            n = len(me.vertices)
            co = np.empty(n * 3, np.float32)
            me.vertices.foreach_get("co", co)
            me.calc_loop_triangles()
            tris = np.empty(len(me.loop_triangles) * 3, np.int32)
            me.loop_triangles.foreach_get("vertices", tris)
            vel = None
            attr = me.attributes.get("velocity")
            if attr is not None and attr.domain == "POINT" and n:
                vel = np.empty(n * 3, np.float32)
                attr.data.foreach_get("vector", vel)
                vel = vel.reshape(n, 3).astype(float)
        finally:
            ev.to_mesh_clear()
        mw = np.array(dom.matrix_world)
        verts = co.reshape(n, 3).astype(float) @ mw[:3, :3].T + mw[:3, 3]
        if vel is not None:
            vel = vel @ mw[:3, :3].T
        return cls(verts, tris.reshape(-1, 3), vel, regions)

    @classmethod
    def from_bobj(cls, path, dom, regions=None):
        """Mantaflow's mesh cache file (.bobj.gz): coordinates are the
        domain's unit cube scaled by its largest dimension (verified on 4.5
        and 5.2 against the evaluated mesh)."""
        raw = gzip.open(path, "rb").read()
        n = struct.unpack_from("<i", raw, 0)[0]
        off = 4
        v = np.frombuffer(raw, "<f4", n * 3, off).reshape(n, 3).astype(float)
        off += n * 12
        nn = struct.unpack_from("<i", raw, off)[0]
        off += 4 + nn * 12
        nt = struct.unpack_from("<i", raw, off)[0]
        t = np.frombuffer(raw, "<i4", nt * 3, off + 4).reshape(nt, 3)
        loc, rot, sca = dom.matrix_world.decompose()
        R = np.array(rot.to_matrix())
        verts = (v * max(abs(s) for s in sca)) @ R.T + np.array(loc[:])
        return cls(verts, t, None, regions)

    def column(self, x, y, top, bottom):
        """Top of the thickest liquid column under (x, y), its velocity."""
        if self.tree is None:
            return None, None
        z, down = top, Vector((0, 0, -1))
        enter, best = None, (0.0, None, None)
        for _ in range(16):
            loc, nrm, idx, _d = self.tree.ray_cast(Vector((x, y, z)), down, z - bottom)
            if loc is None:
                break
            if nrm.z > 0 and enter is None:
                enter = (loc.z, idx)
            elif nrm.z < 0 and enter is not None:
                if enter[0] - loc.z > best[0]:
                    best = (enter[0] - loc.z, enter[0], enter[1])
                enter = None
            z = loc.z - 1e-5
        if enter is not None and enter[0] - bottom > best[0]:
            best = (enter[0] - bottom, enter[0], enter[1])
        if best[1] is None:
            return None, None
        vel = self.vel[self.tris[best[2]]].mean(0) if self.vel is not None else None
        return best[1], vel


class Plane:
    """The water line near a floater: h = h0 + hx (x - cx) + hy (y - cy),
    water velocity u."""

    def __init__(self, cx, cy, h0=-1e9, hx=0.0, hy=0.0, u=None, wet=False):
        self.cx, self.cy, self.h0, self.hx, self.hy = cx, cy, h0, hx, hy
        self.u = np.zeros(3) if u is None else u
        self.wet = wet

    def lerp(self, other, s):
        if not (self.wet and other.wet):
            return other if s > 0.5 else self
        return Plane(self.cx, self.cy, *(a + (b - a) * s for a, b in (
            (self.h0, other.h0), (self.hx, other.hx), (self.hy, other.hy))),
            u=self.u + (other.u - self.u) * s, wet=True)


def sample_plane(surface, body, tank, gap):
    """Least-squares plane through a ring of probes around the body."""
    cx, cy = body.x[0], body.x[1]
    r = body.footprint() + gap
    pts, vels = [], []
    for k in range(body.p["ring_points"]):
        a = 2 * math.pi * k / body.p["ring_points"]
        x = min(max(cx + r * math.cos(a), tank.lo[0]), tank.hi[0])
        y = min(max(cy + r * math.sin(a), tank.lo[1]), tank.hi[1])
        z, vel = surface.column(x, y, tank.hi[2] + 1.0, tank.lo[2] - 1.0)
        if z is not None:
            pts.append((x - cx, y - cy, z))
            if vel is not None:
                vels.append(vel)
    if len(pts) < 3:
        return Plane(cx, cy)
    P = np.array(pts)
    A = np.c_[np.ones(len(P)), P[:, 0], P[:, 1]]
    (h0, hx, hy), *_ = np.linalg.lstsq(A, P[:, 2], rcond=None)
    if np.ptp(P[:, 0]) < 1e-6 or np.ptp(P[:, 1]) < 1e-6:
        h0, hx, hy = P[:, 2].mean(), 0.0, 0.0
    u = np.mean(vels, 0) if vels and body.p["use_water_velocity"] else None
    return Plane(cx, cy, h0, hx, hy, u, True)


class Tank:
    """Inner bounds of the liquid domain (Mantaflow keeps a one-cell
    obstacle border on every side)."""

    def __init__(self, dom):
        from .still_water import object_dims
        mod = next(m for m in dom.modifiers if m.type == "FLUID")
        ds = mod.domain_settings
        dims = object_dims(dom)
        self.cell = max(dims) / ds.resolution_max
        c = Vector(dom.matrix_world.translation)
        self.lo = np.array(c - dims / 2) + self.cell
        self.hi = np.array(c + dims / 2) - self.cell


# ---------------------------------------------------------------------------
# Dynamics
# ---------------------------------------------------------------------------

def _qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array((w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                     w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2))


def _contacts(body, tank, R, m_eff, Iinv):
    p = body.p
    planes = ((np.array((0, 0, 1.0)), tank.lo[2]),
              (np.array((1.0, 0, 0)), tank.lo[0]), (np.array((-1.0, 0, 0)), -tank.hi[0]),
              (np.array((0, 1.0, 0)), tank.lo[1]), (np.array((0, -1.0, 0)), -tank.hi[1]))
    for n, d in planes:
        H = body.hull @ R.T + body.x
        dist = H @ n - d
        pen = dist < 0
        if not pen.any():
            continue
        body.x = body.x + n * (-dist.min())
        r = H[pen].mean(0) - body.x
        vc = body.v + np.cross(body.w, r)
        vn = vc @ n
        if vn >= 0:
            continue
        e = p["restitution"] if vn < -0.3 else 0.0
        rn = np.cross(r, n)
        k = 1 / m_eff + n @ np.cross(Iinv @ rn, r)
        j = -(1 + e) * vn / k
        body.v = body.v + j * n / m_eff
        body.w = body.w + Iinv @ (rn * j)
        vt = vc - vn * n
        st = np.linalg.norm(vt)
        if st > 1e-9:
            t = vt / st
            rt = np.cross(r, t)
            kt = 1 / m_eff + t @ np.cross(Iinv @ rt, r)
            jt = min(st / kt, p["friction"] * j)
            body.v = body.v - jt * t / m_eff
            body.w = body.w - Iinv @ (rt * jt)


def step(body, plane, tank, dt):
    p = body.p
    R = body.rotation()
    r = body.points @ R.T
    P = body.x + r
    decay = 1.0
    if plane.wet:
        h = plane.h0 + plane.hx * (P[:, 0] - plane.cx) + plane.hy * (P[:, 1] - plane.cy)
        if p["wave_number"] > 0:
            # Linear wave pressure below the still level falls off as
            # e^(-k depth): deep parts of the hull feel less of the wave.
            decay = np.exp(-p["wave_number"] * np.clip(p["rest_level"] - P[:, 2], 0.0, None))
            h = p["rest_level"] + (h - p["rest_level"]) * decay
            decay = decay[:, None]
        frac = np.clip((h - P[:, 2]) / body.layer + 0.5, 0.0, 1.0)
    else:
        frac = np.zeros(len(P))
    wv = frac * body.dv
    body.vsub = float(wv.sum())
    force = np.array((0.0, 0.0, -body.mass * GRAVITY))
    torque = np.zeros(3)
    if body.vsub > 0:
        slope = np.array((-plane.hx, -plane.hy, 0.0)) * decay + np.array((0.0, 0.0, 1.0))
        fi = RHO_WATER * GRAVITY * wv[:, None] * slope
        rel = body.v + np.cross(body.w, r) - plane.u
        speed = np.sqrt((rel ** 2).sum(1))
        coef = p["drag_linear"] + p["drag_quadratic"] * speed / body.length
        fi = fi - RHO_WATER * (wv * coef)[:, None] * rel
        force += fi.sum(0)
        torque += np.cross(r, fi).sum(0)
    grow = 1.0 + p["added_mass"] * RHO_WATER * body.vsub / body.mass
    m_eff = body.mass * grow
    Iw = R @ body.inertia @ R.T * grow
    Iinv = R @ body.inertia_inv @ R.T / grow
    body.v = body.v + force / m_eff * dt
    body.w = body.w + Iinv @ (torque - np.cross(body.w, Iw @ body.w)) * dt
    body.x = body.x + body.v * dt
    body.q = body.q + 0.5 * dt * _qmul(np.r_[0.0, body.w], body.q)
    body.q /= np.linalg.norm(body.q)
    _contacts(body, tank, body.rotation(), m_eff, Iinv)


def advance(bodies, plane_pairs, tank, dt_frame):
    """One frame: `plane_pairs[i]` is (water line at the frame start, at
    its end) for bodies[i]."""
    for body, (a, b) in zip(bodies, plane_pairs):
        n = body.p["substeps"]
        for k in range(n):
            step(body, a.lerp(b, (k + 0.5) / n), tank, dt_frame / n)


def _regions(bodies, gap):
    out = []
    for b in bodies:
        r = b.footprint() + gap + 0.15 + float(np.linalg.norm(b.v[:2])) * 0.1
        out.append((b.x[0] - r, b.x[1] - r, b.x[0] + r, b.x[1] + r))
    return out


def _record(body, frame, plane):
    loc, q = body.pose()
    body.track.append(dict(frame=frame, loc=loc, q=q, com=body.x.copy(),
                           vsub=body.vsub, level=plane.h0 if plane.wet else None,
                           slope=(plane.hx, plane.hy), u=plane.u.copy()))


# ---------------------------------------------------------------------------
# One-way bake: read the baked liquid
# ---------------------------------------------------------------------------

def bake(scene, dom, objs, frame_start=None, frame_end=None, params=None,
         densities=None, write=True, initial_velocity=None, progress=None):
    """Simulate `objs` on the baked liquid of `dom`; returns the bodies
    (their .track) and timings.  Keyframes are written when `write`;
    `progress(frame)` is called after every frame."""
    mod = next(m for m in dom.modifiers if m.type == "FLUID")
    ds = mod.domain_settings
    f0 = frame_start if frame_start is not None else ds.cache_frame_start
    f1 = frame_end if frame_end is not None else ds.cache_frame_end
    densities = densities or {}
    scene.frame_set(f0)  # keyed floaters start from their first-frame pose
    bodies = [Body(o, density=densities.get(o.name), params=params) for o in objs]
    for b in bodies:
        if initial_velocity and b.obj.name in initial_velocity:
            b.v = np.array(initial_velocity[b.obj.name], float)
    tank = Tank(dom)
    gap = bodies[0].p["ring_gap_cells"] * tank.cell if bodies else 0.0
    fps = scene.render.fps / scene.render.fps_base
    timing = dict(surface=0.0, dynamics=0.0, frames=0, verts=0)

    def surface_at(frame):
        scene.frame_set(frame)
        t = time.perf_counter()
        surf = Surface.from_domain(dom, bpy.context.evaluated_depsgraph_get(),
                                   _regions(bodies, gap))
        timing["surface"] += time.perf_counter() - t
        timing["verts"] = max(timing["verts"], surf.n_verts)
        return surf

    def planes(surf):
        t = time.perf_counter()
        out = [sample_plane(surf, b, tank, gap) for b in bodies]
        timing["surface"] += time.perf_counter() - t
        return out

    start = surface_at(f0)
    for b, pl in zip(bodies, planes(start)):
        _record(b, f0, pl)
    for f in range(f0, f1):
        end = surface_at(f + 1)
        # Both ends probed where the bodies are now.
        pairs = list(zip(planes(start), planes(end)))
        for a, b in pairs:
            if a.wet and b.wet and not (a.u.any() or b.u.any()):
                # No speed vectors (the add-on's MODULAR/BOBJECT bakes have
                # none): the water line's own vertical speed.
                a.u = b.u = np.array((0.0, 0.0, (b.h0 - a.h0) * fps))
        t = time.perf_counter()
        advance(bodies, pairs, tank, 1.0 / fps)
        timing["dynamics"] += time.perf_counter() - t
        for b, (_a, pl) in zip(bodies, pairs):
            _record(b, f + 1, pl)
        start = end
        timing["frames"] += 1
        if progress is not None:
            progress(f + 1)
    if write:
        for b in bodies:
            write_keyframes(b)
    return bodies, timing


# ---------------------------------------------------------------------------
# Two-way bake: floaters move inside Mantaflow's own bake loop
# ---------------------------------------------------------------------------

class CoupledBake:
    """Use as a context manager around a BLOCKING bake (EXEC_DEFAULT):

        with CoupledBake(scene, dom, objs) as cb:
            bpy.ops.fluid.bake_all()

    Each new frame f: read <cache>/mesh/fluid_mesh_<f-1>.bobj.gz, advance
    the floaters one frame on that surface (held over the frame; the
    surface's vertical speed comes from the last two frames), and key
    their new pose so the effector reads it.  The solver is one frame
    behind the floaters — the same lag a sequential fluid/rigid scheme has.
    """

    def __init__(self, scene, dom, objs, params=None, densities=None,
                 initial_velocity=None, progress=None):
        self.scene, self.dom = scene, dom
        mod = next(m for m in dom.modifiers if m.type == "FLUID")
        self.ds = mod.domain_settings
        densities = densities or {}
        scene.frame_set(self.ds.cache_frame_start)
        self.bodies = [Body(o, density=densities.get(o.name), params=params) for o in objs]
        for b in self.bodies:
            if initial_velocity and b.obj.name in initial_velocity:
                b.v = np.array(initial_velocity[b.obj.name], float)
        self.tank = Tank(dom)
        self.gap = self.bodies[0].p["ring_gap_cells"] * self.tank.cell
        self.fps = scene.render.fps / scene.render.fps_base
        self.last = None
        self.prev_planes = None
        self.timing = dict(surface=0.0, dynamics=0.0, frames=0, verts=0, wait=0.0)
        self.started = None
        self.progress = progress

    def _mesh_path(self, frame):
        root = bpy.path.abspath(self.ds.cache_directory)
        return os.path.join(root, "mesh", f"fluid_mesh_{frame:04d}.bobj.gz")

    def _handler(self, scene, _dg=None):
        f = scene.frame_current
        if self.last is None or f != self.last + 1:
            if f == self.ds.cache_frame_start and self.last is None:
                self.last = f
                for b in self.bodies:
                    _record(b, f, Plane(0, 0))
            return
        path = self._mesh_path(f - 1)
        if not os.path.isfile(path) or os.path.getmtime(path) < self.started:
            return
        t = time.perf_counter()
        surf = Surface.from_bobj(path, self.dom, _regions(self.bodies, self.gap))
        planes = [sample_plane(surf, b, self.tank, self.gap) for b in self.bodies]
        self.timing["surface"] += time.perf_counter() - t
        self.timing["verts"] = max(self.timing["verts"], surf.n_verts)
        t = time.perf_counter()
        pairs = []
        for i, pl in enumerate(planes):
            prev = self.prev_planes[i] if self.prev_planes else None
            if pl.wet and prev is not None and prev.wet:
                # Vertical water speed from the last two frames (the mesh
                # cache carries no speed vectors).
                pl.u = pl.u + np.array((0, 0, (pl.h0 - prev.h0) * self.fps))
            ahead = Plane(pl.cx, pl.cy, pl.h0 + pl.u[2] / self.fps, pl.hx, pl.hy,
                          pl.u, pl.wet)
            pairs.append((pl, ahead))
        advance(self.bodies, pairs, self.tank, 1.0 / self.fps)
        for b, pl in zip(self.bodies, planes):
            _record(b, f, pl)
            _set_key(b, f - self.ds.cache_frame_start, b.track[-1])
        self.prev_planes = planes
        self.timing["dynamics"] += time.perf_counter() - t
        self.timing["frames"] += 1
        self.last = f
        if self.progress is not None:
            self.progress(f)

    def __enter__(self):
        self.started = time.time() - 1.0
        # Every frame is keyed BEFORE the bake; the handler only edits the
        # key values.  Writing to the object during the bake (its location,
        # or keyframe_insert) resets Mantaflow's record of the effector's
        # motion: it then moves without velocity and deletes the water it
        # enters instead of pushing it (Blender 4.5: -0.84% volume against
        # +0.04% for the same motion keyed in advance).
        first, last = self.ds.cache_frame_start, self.ds.cache_frame_end
        for b in self.bodies:
            _prepare_keys(b, first, last)
        bpy.app.handlers.frame_change_pre.append(self._handler)
        return self

    def __exit__(self, *exc):
        if self._handler in bpy.app.handlers.frame_change_pre:
            bpy.app.handlers.frame_change_pre.remove(self._handler)
        for b in self.bodies:
            for fc in getattr(b, "_keys", {}).values():
                fc.update()
        return False


# ---------------------------------------------------------------------------
# Keyframes and restore
# ---------------------------------------------------------------------------

def _begin_keys(body):
    """Record the object's pre-bake state once, give it our own action."""
    obj = body.obj
    if RESTORE_PROP not in obj.keys():
        ad = obj.animation_data
        obj[RESTORE_PROP] = json.dumps(dict(
            location=list(obj.location), rotation_mode=obj.rotation_mode,
            rotation_euler=list(obj.rotation_euler),
            rotation_quaternion=list(obj.rotation_quaternion),
            had_animation_data=ad is not None))
        if ad is not None and ad.action is not None:
            obj[PREV_ACTION_PROP] = ad.action
    ad = obj.animation_data or obj.animation_data_create()
    old = ad.action
    if old is not None and old.get(C.OWNER_PROP, "").startswith("FLOAT:"):
        ad.action = None
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(f"AQS_Float_{obj.name}")
    act[C.OWNER_PROP] = "FLOAT:" + obj.name
    ad.action = act


def _rotation_values(obj, q, prev):
    if obj.rotation_mode == "QUATERNION":
        if prev is not None and np.dot(prev, q) < 0:
            q = -q
        return "rotation_quaternion", tuple(q)
    if obj.rotation_mode == "AXIS_ANGLE":
        axis, ang = Quaternion(q).to_axis_angle()
        return "rotation_axis_angle", (ang, *axis)
    quat = Quaternion(q)
    e = quat.to_euler(obj.rotation_mode) if prev is None \
        else quat.to_euler(obj.rotation_mode, prev)
    return "rotation_euler", tuple(e)


def _fcurves(obj):
    """{(data_path, index): F-curve} of the object's action (layered
    actions on 4.4+, where Action.fcurves is gone in 5.x)."""
    ad = obj.animation_data
    act = ad.action
    fcurves = None
    try:
        from bpy_extras import anim_utils
        bag = anim_utils.action_get_channelbag_for_slot(act, ad.action_slot)
        fcurves = bag.fcurves if bag is not None else None
    except (ImportError, AttributeError):
        pass
    if fcurves is None:
        fcurves = act.fcurves
    return {(fc.data_path, fc.array_index): fc for fc in fcurves}


def _prepare_keys(body, first, last):
    """Our own action with a LINEAR key on every frame first..last for
    location and rotation, all at the current pose."""
    _begin_keys(body)
    obj = body.obj
    path = _rotation_values(obj, body.q, None)[0]
    obj.keyframe_insert("location", frame=first)
    obj.keyframe_insert(path, frame=first)
    n = last - first + 1
    for fc in _fcurves(obj).values():
        if fc.data_path not in ("location", path):
            continue
        v = fc.keyframe_points[0].co[1]
        fc.keyframe_points.add(n - 1)
        co = np.empty(2 * n)
        co[0::2] = np.arange(first, last + 1)
        co[1::2] = v
        for attr in ("co", "handle_left", "handle_right"):
            fc.keyframe_points.foreach_set(attr, co)
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    body._keys = _fcurves(obj)
    body._rot_path = path
    body._prev_rot = None


def _set_key(body, index, entry):
    """Write one pose into the prepared keys (no write to the object)."""
    obj = body.obj
    path, val = _rotation_values(obj, entry["q"], body._prev_rot)
    body._prev_rot = Euler(val, obj.rotation_mode) if path == "rotation_euler" else np.array(val)
    for (p, i), fc in body._keys.items():
        v = entry["loc"][i] if p == "location" else val[i] if p == path else None
        if v is None or index >= len(fc.keyframe_points):
            continue
        kp = fc.keyframe_points[index]
        kp.co[1] = kp.handle_left[1] = kp.handle_right[1] = float(v)


def write_keyframes(body):
    track = body.track
    _prepare_keys(body, track[0]["frame"], track[-1]["frame"])
    for i, entry in enumerate(track):
        _set_key(body, i, entry)
    for fc in body._keys.values():
        fc.update()


def clear(obj):
    """Remove the floater keyframes and restore the object as it was."""
    ad = obj.animation_data
    if ad is not None and ad.action is not None \
            and ad.action.get(C.OWNER_PROP, "").startswith("FLOAT:"):
        act = ad.action
        ad.action = None
        bpy.data.actions.remove(act)
    try:
        rec = json.loads(obj.get(RESTORE_PROP, "{}"))
    except Exception:
        rec = {}
    if rec:
        prev = obj.get(PREV_ACTION_PROP)
        if prev is not None:
            (obj.animation_data or obj.animation_data_create()).action = prev
        elif not rec.get("had_animation_data") and obj.animation_data is not None:
            obj.animation_data_clear()
        obj.rotation_mode = rec["rotation_mode"]
        obj.location = rec["location"]
        obj.rotation_euler = rec["rotation_euler"]
        obj.rotation_quaternion = rec["rotation_quaternion"]
    for prop in (RESTORE_PROP, PREV_ACTION_PROP):
        if prop in obj.keys():
            del obj[prop]


# ---------------------------------------------------------------------------
# "Pushes water": a Fluid effector that is NOT a Water Obstacle
# ---------------------------------------------------------------------------

def set_pushes_water(obj, on, surface_distance=0.0, subframes=0):
    """Give the floater its own collision effector (marked with
    EFFECTOR_PROP, so the Water Obstacles sync never touches it), or remove
    the one we added.  A closed floater needs no extra thickness: any
    surface distance displaces surface area x distance more water."""
    if on:
        if not any(m.type == "FLUID" for m in obj.modifiers):
            from ..core import obstacles
            obstacles.add_fluid_effector(obj, "AQS Floater Effector")
            obj[EFFECTOR_PROP] = True
        mod = next(m for m in obj.modifiers if m.type == "FLUID")
        if not obj.get(EFFECTOR_PROP):
            # The user's own Fluid modifier: leave its settings alone.
            return mod
        es = mod.effector_settings
        es.surface_distance = surface_distance
        es.subframes = subframes
        if hasattr(es, "use_effector"):
            es.use_effector = True
        return mod
    if obj.get(EFFECTOR_PROP):
        for m in list(obj.modifiers):
            if m.type == "FLUID" and getattr(m, "fluid_type", "") == "EFFECTOR":
                obj.modifiers.remove(m)
                break
        del obj[EFFECTOR_PROP]
    return None
