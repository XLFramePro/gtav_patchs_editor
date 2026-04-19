"""
================================================================================
GTA V Pathing Editor — Blender 4.5 Addon
================================================================================
Supporte les formats :
  • YNV  — NavMesh (polygones piétons/véhicules, portails, points de nav)
  • YND  — NodeDictionary (noeuds de chemin véhicules/piétons, liens)
  • YMT  — ScenarioPointRegion (spawn points, chaining graph, clusters)
  • TRAINS.DAT — Pistes de train (points 3D avec flags)

Chaque format a ses propres propriétés, opérateurs, import/export XML/.dat
et visualisation GPU dans le viewport 3D.
================================================================================
"""

bl_info = {
    "name":        "GTA V Pathing Editor",
    "author":      "XLTeam SDK",
    "version":     (1, 0, 0),
    "blender":     (4, 5, 0),
    "location":    "View3D > N-Panel > GTA5 Paths",
    "description": "Éditeur complet YNV/YND/YMT/Trains pour GTA V",
    "category":    "Import-Export",
}

import bpy

from . import (
    properties,
    operators_ynv,
    operators_ynd,
    operators_ymt,
    operators_trains,
    ui,
    draw_handler,
)

_modules = [
    properties,
    operators_ynv,
    operators_ynd,
    operators_ymt,
    operators_trains,
    ui,
    draw_handler,
]


def _start_click_handler():
    """Lance le modal de clic-sélection s'il n'est pas déjà actif."""
    import bpy
    # Vérifier si déjà actif
    wm = bpy.context.window_manager
    if wm and hasattr(wm, "operators"):
        for op in wm.operators:
            if op.bl_idname == "gta5_ynd.activate_click_select":
                return
    # Lancer le modal via le window manager
    try:
        bpy.ops.gta5_ynd.activate_click_select("INVOKE_DEFAULT")
    except Exception:
        pass


def register():
    for mod in _modules:
        mod.register()
    # Démarrer le handler de clic après un court délai
    import bpy
    bpy.app.timers.register(_start_click_handler, first_interval=0.5)
    print("[GTA5 Pathing Editor] Addon enregistré.")


def unregister():
    for mod in reversed(_modules):
        mod.unregister()
    print("[GTA5 Pathing Editor] Addon désactivé.")


if __name__ == "__main__":
    register()
