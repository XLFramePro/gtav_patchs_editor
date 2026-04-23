"""
================================================================================
GTA V Pathing Editor — Blender 4.5 Addon
================================================================================
Supports formats:
  • YNV  — NavMesh (pedestrian/vehicle polygons, portals, nav points)
  • YND  — NodeDictionary (vehicle/pedestrian path nodes, links)
  • YMT  — ScenarioPointRegion (spawn points, chaining graph, clusters)
  • TRAINS.DAT — Train tracks (3D points with flags)

Each format has its own properties, operators, XML/.dat import/export
and GPU visualization in the 3D viewport.
================================================================================
"""

bl_info = {
    "name":        "GTA V Pathing Editor",
    "author":      "XLTeam SDK",
    "version":     (1, 0, 0),
    "blender":     (4, 5, 0),
    "location":    "View3D > N-Panel > GTA5 Paths",
    "description": "Complete YNV/YND/YMT/Trains editor for GTA V",
    "category":    "Import-Export",
}

import bpy

from . import (
    shared,
    ynv,
    ynd,
    ymt,
    trains,
    panels,
    viewport,
)

_modules = [
    shared,
    ynv,
    ynd,
    ymt,
    trains,
    panels,
    viewport,
]


def _start_click_handler():
    """Launch the click-select modal if not already active."""
    # Check if already active
    wm = bpy.context.window_manager
    if wm and hasattr(wm, "operators"):
        for op in wm.operators:
            if op.bl_idname == "gta5_ynd.activate_click_select":
                return
    # Launch modal via window manager
    try:
        bpy.ops.gta5_ynd.activate_click_select("INVOKE_DEFAULT")
    except Exception:
        pass


def register():
    for mod in _modules:
        mod.register()
    # Start click handler after short delay
    bpy.app.timers.register(_start_click_handler, first_interval=0.5)
    print("[GTA5 Pathing Editor] Addon registered.")


def unregister():
    for mod in reversed(_modules):
        mod.unregister()
    print("[GTA5 Pathing Editor] Addon unregistered.")


if __name__ == "__main__":
    register()
