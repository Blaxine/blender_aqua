# SPDX-License-Identifier: GPL-3.0-or-later
"""Real liquids for Still Water: what each is made of -> solver settings.

Viscosity and density are typical room-temperature figures; real batches vary
widely.  Everything else is calculated from them and the size of the mesh:

* A 2 m block of real honey is runny: viscosity matters less the bigger the
  flow.  Beginners' meshes are rarely to scale, so a mesh is treated as a
  REFERENCE_SIZE pour seen larger.  Keeping the Galilei number g L^3 / nu^2
  the same at any size gives  nu_sim = nu * (size / REFERENCE_SIZE) ^ 1.5.
* The solver's viscosity is relative to the domain and its own time unit:
  value = nu_sim * SOLVER_TIME / domain_size^2.
"""

import math

REFERENCE_SIZE = 0.1      # m: a mesh this size or smaller gets the real viscosity
# s per solver time unit.  Measured (Blender 5.1, 1 m cube collapsing, spread
# radius after 3 s; the 1/L^2 and fps terms are why nothing else appears here):
# value 0.01 in a 4 m domain at resolution 48: 1.53 m; value 0.0025 in 8 m at
# 96 (same cells, same nu): 1.53 m; at 48 fps: 1.49 m; at resolution 96: 1.42 m.
# Against the gravity-current law r = 0.894 (g V^3 t / 3 nu)^(1/8), 0.4 fits
# value 0.05 and overstates value 0.01 threefold, which is 15% in radius.
SOLVER_TIME = 0.4
MIN_VISCOSITY = 1e-5      # below this the viscosity solver only costs bake time
MAX_VISCOSITY = 10.0      # the property's hard limit
WATER_NU = 1e-6           # m^2/s
# A splashing liquid gains volume at Blender's default particle radius of 1.0.
# Measured (Blender 5.1), a 2 m cube (8 m^3) dropped in its domain, 120 frames:
# Water 27.6 m^3 at 1.0, 12.8 at 0.8, 8.2 at 0.7, 6.4 at 0.6; at 0.7 also 7.9 at
# resolution 48 and 9.5 at 96; Oil 8.4.  Liquids at least this thick barely
# splash and keep their volume at 1.0 (Honey 8.7).
THIN_NU = 1e-3            # m^2/s
THIN_PARTICLE_RADIUS = 0.7
PREFIX = "STILL_"         # preset id = PREFIX + liquid key

# viscosity: Pa*s.  density: kg/m^3.  look: None is the default water material;
# CLEAR is glass with coloured absorption (density per metre at REFERENCE_SIZE);
# OPAQUE is a Principled surface; bumps = lumps across the mesh.
LIQUIDS = {
    "WATER": dict(label="Water", viscosity=0.001, density=1000.0, look=None),
    "SYRUP": dict(label="Syrup", viscosity=2.5, density=1330.0, look=dict(
        kind="CLEAR", ior=1.45, color=(0.83, 0.54, 0.0), absorption=46.0)),
    "OIL": dict(label="Oil", viscosity=0.08, density=915.0, look=dict(
        kind="CLEAR", ior=1.47, color=(0.95, 0.78, 0.0), absorption=10.0)),
    "CHOCOLATE": dict(label="Chocolate", viscosity=8.0, density=1300.0, look=dict(
        kind="OPAQUE", color=(0.03, 0.009, 0.003), roughness=0.25, subsurface=0.0, specular=0.3)),
    "THICK_CREAM": dict(label="Thick Cream", viscosity=1.5, density=1000.0, look=dict(
        kind="OPAQUE", color=(0.93, 0.87, 0.72), roughness=0.38, subsurface=0.5)),
    "CREAM": dict(label="Cream", viscosity=0.02, density=1010.0, look=dict(
        kind="OPAQUE", color=(0.95, 0.91, 0.8), roughness=0.25, subsurface=0.6)),
    "OATMEAL": dict(label="Oatmeal", viscosity=30.0, density=1100.0, look=dict(
        kind="OPAQUE", color=(0.42, 0.27, 0.12), roughness=0.75, subsurface=0.2, bumps=20.0)),
    "HONEY": dict(label="Honey", viscosity=10.0, density=1420.0, look=dict(
        kind="CLEAR", ior=1.49, color=(0.95, 0.73, 0.0), absorption=30.0)),
}


def preset_id(key):
    return PREFIX + key


def kinematic(key):
    """nu = viscosity / density, m^2/s."""
    liquid = LIQUIDS[key]
    return liquid["viscosity"] / liquid["density"]


def simulated_nu(key, size):
    """The viscosity that makes a mesh of this size flow like a
    REFERENCE_SIZE pour of the real liquid."""
    return kinematic(key) * max(size / REFERENCE_SIZE, 1.0) ** 1.5


def solver_viscosity(key, size, domain_size):
    """The domain's viscosity_value, or 0 when the liquid is runny enough to
    leave the viscosity solver off."""
    value = simulated_nu(key, size) * SOLVER_TIME / max(domain_size, 1e-6) ** 2
    return min(value, MAX_VISCOSITY) if value >= MIN_VISCOSITY else 0.0


def flip_ratio(key):
    """Lower FLIP keeps thick liquids from sloshing: 0.97 for water, losing
    0.12 per tenfold rise in viscosity."""
    return round(max(0.97 - 0.12 * math.log10(max(kinematic(key) / WATER_NU, 1.0)), 0.3), 3)


def particle_radius(key):
    return THIN_PARTICLE_RADIUS if kinematic(key) < THIN_NU else 1.0


def mesh_size(entry):
    """Largest extent of any water mesh in this setup, in metres."""
    from ..level2 import still_water as sw
    size = 0.0
    for obj in sw.water_sources(entry):
        mins, maxs = sw.world_bbox(obj)
        size = max(size, *(maxs - mins))
    return size


def apply_physics(entry, ds, key):
    """Set the domain's viscosity for this liquid and the current sizes."""
    from ..level2 import still_water as sw
    dom = sw.find_domain_object(entry)
    value = solver_viscosity(key, mesh_size(entry), max(sw.object_dims(dom)))
    sw.set_flag(ds, "use_viscosity", value > 0.0)
    if value > 0.0:
        ds.viscosity_value = value


def apply_look(entry, key):
    """Give the setup's own liquid material this look; a material the user
    assigned instead is left alone."""
    from . import naming
    from ..level2 import still_water as sw
    from ..materials import mats
    dom = sw.find_domain_object(entry)
    if dom is None:
        return
    size = mesh_size(entry)
    for slot in dom.material_slots:
        if slot.material is not None and naming.owned_by(slot.material, entry.uuid):
            mats.set_liquid_look(slot.material, key, LIQUIDS[key]["look"],
                                 size, REFERENCE_SIZE)


def describe(key):
    liquid = LIQUIDS[key]
    return f'{liquid["viscosity"]:g} Pa·s · {liquid["density"]:.0f} kg/m³'


def solver_note(entry, ds):
    """What the calculation did for this mesh, for the Advanced view."""
    size = mesh_size(entry)
    if not ds.use_viscosity:
        return f"Viscosity solver off · {size:.2g} m mesh"
    return f"Solver viscosity {ds.viscosity_value:.2g} · {size:.2g} m mesh"
