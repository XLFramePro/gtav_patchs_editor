"""
GTA V Pathing Editor — v4.1
============================
Import / Edit / Export: YNV · YND · YMT · Trains
Blender 4.5+
"""

bl_info = {
    "name":        "GTA V Pathing Editor",
    "author":      "XLTeam SDK",
    "version":     (4, 1, 0),
    "blender":     (4, 5, 0),
    "location":    "View3D › N-Panel › GTA5 PE",
    "description": "Import / Edit / Export  YNV · YND · YMT · Trains for GTA V / FiveM",
    "category":    "Import-Export",
}

import bpy
from . import props, ops_ynv, ops_ynd, ops_ymt, ops_trains, viewport, ui

_MODULES = [props, ops_ynv, ops_ynd, ops_ymt, ops_trains, viewport, ui]


def _launch_modals():
    """Start lightweight modals for tracking active objects (YND/YMT/Trains)."""
    for op in ("gta5pe.ynd_track_active",
               "gta5pe.ymt_track_active",
               "gta5pe.trains_track_active"):
        try:
            getattr(bpy.ops, op.replace(".", "_"))("INVOKE_DEFAULT")
        except Exception:
            pass
    # Alternative direct calls:
    try: bpy.ops.gta5pe.ynd_track_active("INVOKE_DEFAULT")
    except Exception: pass
    try: bpy.ops.gta5pe.ymt_track_active("INVOKE_DEFAULT")
    except Exception: pass
    try: bpy.ops.gta5pe.trains_track_active("INVOKE_DEFAULT")
    except Exception: pass


def _poll_active_face():
    """Timer: auto-read navmesh face flags when in Edit Mode on a YNV mesh.
    Only runs bmesh operations when actually needed (tab=YNV + edit mode).
    Interval: 0.2s to reduce CPU overhead."""
    try:
        ctx = bpy.context
        # Fast bail-out: skip if not on YNV tab or not in edit mode
        if not hasattr(ctx, "scene") or not hasattr(ctx.scene, "gta5pe"):
            return 0.2
        if ctx.scene.gta5pe.tab != "YNV":
            return 0.2
        obj = ctx.active_object
        if not obj or obj.type != "MESH" or obj.mode != "EDIT":
            return 0.2
        if not obj.get("ynv_type") == "poly_mesh":
            return 0.2
        # Only now do the expensive bmesh call
        from .ops_ynv import _on_edit_mode_change
        _on_edit_mode_change()
    except Exception:
        pass
    return 0.2


def register():
    for m in _MODULES:
        m.register()
    bpy.app.timers.register(_launch_modals,    first_interval=1.0)
    bpy.app.timers.register(_poll_active_face, first_interval=2.0, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(_poll_active_face):
        bpy.app.timers.unregister(_poll_active_face)
    for m in reversed(_MODULES):
        m.unregister()
