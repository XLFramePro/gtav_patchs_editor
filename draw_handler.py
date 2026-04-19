"""
draw_handler.py — Visualisation GPU YND/YNV/YMT/Trains.

RENDU YND (correspondant à l'image CodeWalker) :
  ● Noeuds blancs (carrés = véhicule, petits ronds = piéton)
  ● Noeud sélectionné = jaune

  OVERLAYS COLORÉS LE LONG DES LIENS (inspiré CodeWalker) :
    ■ VERT  = voies forward (largeur ∝ forward_lanes, min 1)
    ■ ROUGE = voies back    (largeur ∝ back_lanes)

  LIGNES DE LIENS :
    ─ BLEU    = lien véhicule standard
    ─ CYAN    = lien shortcut / slip lane
    ─ ROUGE   = lien piéton / disabled
    ─ MAGENTA = lien parking special
    ─ MARRON  = lien freeway
    ─ ORANGE  = lien dead-end
    ─ JAUNE   = lien vitesse lente (Speed=SLOW)

  FLÈCHES DE DIRECTION le long de chaque lien

  □ VIOLET = junction bounds

CLIC SUR NOEUD → sélection automatique dans le panneau
"""

import bpy
import gpu
import math
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

_handle      = None
_handle_3d   = None   # handler pour le picking par rayon

# ── COULEURS ──────────────────────────────────────────────────────────────────
# Overlays de voies
C_FWD_LANE    = (0.05, 0.70, 0.05, 0.35)   # vert transparent
C_BACK_LANE   = (0.55, 0.08, 0.02, 0.35)   # rouge-brun transparent
# Liens
C_VEH         = (0.25, 0.55, 1.00, 1.0)    # bleu
C_SHORTCUT    = (0.00, 0.85, 1.00, 1.0)    # cyan
C_PED         = (0.90, 0.10, 0.10, 1.0)    # rouge
C_PARKING     = (0.85, 0.00, 0.85, 1.0)    # magenta
C_FREEWAY     = (0.40, 0.12, 0.02, 1.0)    # marron
C_DEAD_END    = (1.00, 0.50, 0.00, 1.0)    # orange
C_SLOW        = (0.90, 0.90, 0.10, 1.0)    # jaune
# Noeuds
C_NODE_VEH    = (1.00, 1.00, 1.00, 1.0)    # blanc
C_NODE_PED    = (0.80, 0.80, 0.80, 0.8)    # blanc grisé
C_SELECTED    = (1.00, 0.88, 0.00, 1.0)    # jaune vif
# Autres
C_JUNCTION    = (0.55, 0.00, 0.85, 0.55)   # violet
C_YMT_CHAIN   = (1.00, 0.85, 0.15, 0.9)
C_TRAINS      = (0.40, 0.40, 0.40, 0.9)
C_TRAIN_JCT   = (1.00, 0.40, 0.00, 1.0)
C_YNV_BB      = (0.20, 0.80, 1.00, 0.5)

PED_TYPES = {"PED_CROSSING", "PED_ASSISTED", "PED_NOWAIT"}

LANE_WIDTH = 1.8   # largeur de base par voie en unités Blender


def _set_lw(w):
    try: gpu.state.line_width_set(w)
    except Exception: pass

def _set_ps(s):
    try: gpu.state.point_size_set(s)
    except Exception: pass


def _draw_lines(shader, verts, color, width=1.5):
    if len(verts) < 2: return
    _set_lw(width)
    batch_for_shader(shader, "LINES", {"pos": verts}).draw(shader)
    shader.uniform_float("color", color)
    batch_for_shader(shader, "LINES", {"pos": verts}).draw(shader)


def _draw_tris(shader, verts, color):
    """Dessine des triangles remplis (pour les overlays de voies)."""
    if len(verts) < 3: return
    batch_for_shader(shader_uniform, "TRIS", {"pos": verts}).draw(shader_uniform)


def _draw_pts(shader, verts, color, size=6.0):
    if not verts: return
    _set_ps(size)
    shader.uniform_float("color", color)
    batch_for_shader(shader, "POINTS", {"pos": verts}).draw(shader)


def _batch_lines(shader, verts, color, width=1.5):
    if len(verts) < 2: return
    _set_lw(width)
    shader.uniform_float("color", color)
    batch_for_shader(shader, "LINES", {"pos": verts}).draw(shader)


def _batch_lines_strip(shader, verts, color, width=2.0):
    if len(verts) < 2: return
    _set_lw(width)
    shader.uniform_float("color", color)
    batch_for_shader(shader, "LINE_STRIP", {"pos": verts}).draw(shader)


def _batch_pts(shader, verts, color, size=6.0):
    if not verts: return
    _set_ps(size)
    shader.uniform_float("color", color)
    batch_for_shader(shader, "POINTS", {"pos": verts}).draw(shader)


def _batch_tris(shader, verts, color):
    """Dessine une liste de triangles (tris consécutifs)."""
    if len(verts) < 3: return
    shader.uniform_float("color", color)
    batch_for_shader(shader, "TRIS", {"pos": verts}).draw(shader)


# ── GÉOMÉTRIE ─────────────────────────────────────────────────────────────────

def _lane_quad(pos_a, pos_b, offset, half_w):
    """
    Retourne 6 vertices (2 triangles) formant un rectangle le long d'un lien.
    offset  = décalage latéral du centre du rectangle (peut être négatif)
    half_w  = demi-largeur du rectangle
    """
    ax, ay, az = pos_a; bx, by, bz = pos_b
    dx, dy, dz = bx-ax, by-ay, bz-az
    length = math.sqrt(dx*dx + dy*dy + dz*dz)
    if length < 0.01: return []
    nx, ny = -dy/length, dx/length   # perpendiculaire 2D

    # Les 4 coins du rectangle
    ox, oy = nx*offset, ny*offset
    wx, wy = nx*half_w, ny*half_w

    v0 = (ax + ox - wx, ay + oy - wy, az)
    v1 = (ax + ox + wx, ay + oy + wy, az)
    v2 = (bx + ox + wx, by + oy + wy, bz)
    v3 = (bx + ox - wx, by + oy - wy, bz)

    return [v0, v1, v2,  v0, v2, v3]   # 2 triangles


def _arrows_along(pos_a, pos_b, spacing=8.0, size=2.0):
    """
    Génère des flèches (chevrons) le long d'un lien, espacées régulièrement.
    """
    ax, ay, az = pos_a; bx, by, bz = pos_b
    dx, dy, dz = bx-ax, by-ay, bz-az
    length = math.sqrt(dx*dx + dy*dy + dz*dz)
    if length < spacing: return []
    ux, uy = dx/length, dy/length
    nx, ny = -uy, ux   # perpendiculaire

    result = []
    num = max(1, int(length / spacing))
    for i in range(1, num + 1):
        t  = i / (num + 1)
        cx = ax + dx*t; cy = ay + dy*t; cz = az + dz*t
        # Chevron : deux demi-branches
        s = size * 0.6
        lx = cx - ux*s + nx*s*0.5; ly = cy - uy*s + ny*s*0.5
        rx = cx - ux*s - nx*s*0.5; ry = cy - uy*s - ny*s*0.5
        result.extend([(lx,ly,cz),(cx,cy,cz), (rx,ry,cz),(cx,cy,cz)])
    return result


def _jct_rect(pos, r=6.0):
    """Rectangle de junction autour d'un point."""
    x, y, z = pos
    return [
        (x-r,y-r,z),(x+r,y-r,z), (x+r,y-r,z),(x+r,y+r,z),
        (x+r,y+r,z),(x-r,y+r,z), (x-r,y+r,z),(x-r,y-r,z),
    ]


# ── PICKING : SÉLECTION AU CLIC ───────────────────────────────────────────────

def _find_closest_node_index(props, ray_origin, ray_dir, max_dist=8.0):
    """
    Trouve le noeud le plus proche du rayon de la caméra.
    Retourne l'index dans props.nodes ou -1.
    """
    best_idx  = -1
    best_dist = max_dist

    for i, node in enumerate(props.nodes):
        pos = Vector(node.position)
        # Distance du point au rayon
        to_pos = pos - ray_origin
        proj   = to_pos.dot(ray_dir)
        if proj < 0: continue
        closest = ray_origin + ray_dir * proj
        d = (pos - closest).length
        if d < best_dist:
            best_dist = d
            best_idx  = i

    return best_idx


class YND_OT_ClickSelectNode(bpy.types.Operator):
    """Clic dans le viewport pour sélectionner un noeud YND"""
    bl_idname  = "gta5_ynd.click_select_node"
    bl_label   = "Sélectionner Noeud YND"
    bl_options = set()   # pas REGISTER pour éviter spam historique

    @classmethod
    def poll(cls, context):
        if not hasattr(context.scene, "gta5_pathing"): return False
        return context.scene.gta5_pathing.active_module == "YND"

    def invoke(self, context, event):
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            props = context.scene.gta5_pathing.ynd
            if not props.nodes: return {"PASS_THROUGH"}

            # Construire le rayon depuis la souris
            region = context.region
            rv3d   = context.region_data
            coord  = (event.mouse_region_x, event.mouse_region_y)

            from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
            ray_origin = region_2d_to_origin_3d(region, rv3d, coord)
            ray_dir    = region_2d_to_vector_3d(region, rv3d, coord).normalized()

            idx = _find_closest_node_index(props, ray_origin, ray_dir, max_dist=12.0)
            if idx >= 0:
                props.node_index = idx
                # Forcer le redraw du panneau
                for area in context.screen.areas:
                    if area.type in ("VIEW_3D", "PROPERTIES"):
                        area.tag_redraw()
                return {"FINISHED"}

        return {"PASS_THROUGH"}

    def modal(self, context, event):
        return {"PASS_THROUGH"}


class YND_OT_ActivateClickSelect(bpy.types.Operator):
    """Active le mode sélection au clic pour les noeuds YND"""
    bl_idname = "gta5_ynd.activate_click_select"
    bl_label  = "Activer Clic-Sélection"
    bl_options = set()

    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if not hasattr(context.scene, "gta5_pathing"):
            return {"CANCELLED"}
        if context.scene.gta5_pathing.active_module != "YND":
            return {"PASS_THROUGH"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            # Vérifier qu'on est dans un viewport 3D
            region_under = None
            for area in context.screen.areas:
                if area.type == "VIEW_3D":
                    for region in area.regions:
                        if region.type == "WINDOW":
                            mx = event.mouse_x - region.x
                            my = event.mouse_y - region.y
                            if 0 <= mx < region.width and 0 <= my < region.height:
                                region_under = (area, region)
                                break

            if region_under:
                area, region = region_under
                rv3d = area.spaces.active.region_3d
                props = context.scene.gta5_pathing.ynd

                coord = (event.mouse_x - region.x, event.mouse_y - region.y)
                from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
                try:
                    ray_origin = region_2d_to_origin_3d(region, rv3d, coord)
                    ray_dir    = region_2d_to_vector_3d(region, rv3d, coord).normalized()
                    idx = _find_closest_node_index(props, ray_origin, ray_dir, max_dist=15.0)
                    if idx >= 0:
                        props.node_index = idx
                        for a in context.screen.areas:
                            a.tag_redraw()
                except Exception:
                    pass

        return {"PASS_THROUGH"}


# ── DRAW PRINCIPAL ─────────────────────────────────────────────────────────────

def _draw_viewport():
    context = bpy.context
    if not hasattr(context, "scene"): return
    if not hasattr(context.scene, "gta5_pathing"): return

    gp     = context.scene.gta5_pathing
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")
    shader.bind()

    active  = gp.active_module

    # ════════════════════════════════════════════════════════════════════════
    #  YND
    # ════════════════════════════════════════════════════════════════════════
    if active == "YND":
        props   = gp.ynd
        sel_idx = props.node_index

        # ── Construire l'index des positions ────────────────────────────────
        node_pos  = {}
        node_ped  = {}
        node_free = {}

        for i, node in enumerate(props.nodes):
            key = (node.area_id, node.node_id)
            node_pos[key] = tuple(node.position)
            try:
                node_ped[key]  = node.flags1.special_type in PED_TYPES
                node_free[key] = node.flags2.freeway
            except Exception:
                node_ped[key]  = False
                node_free[key] = False

        # ── Listes de géométrie ─────────────────────────────────────────────
        tris_fwd   = []   # overlays verts (forward lanes)
        tris_back  = []   # overlays rouges (back lanes)
        tris_jct   = []   # overlays violets (junctions)

        lines_veh     = []
        lines_shortcut= []
        lines_ped_lk  = []
        lines_freeway = []
        lines_dead    = []
        lines_slow    = []
        lines_parking = []
        arrows        = []

        pts_veh  = []
        pts_ped  = []
        pts_sel  = []
        pts_jct  = []

        for i, node in enumerate(props.nodes):
            pos_a = tuple(node.position)
            key_a = (node.area_id, node.node_id)

            try:
                is_ped = node.flags1.special_type in PED_TYPES
                is_fwy = node.flags2.freeway
                is_jct = node.flags2.junction
                speed  = node.flags5.speed
            except Exception:
                is_ped = False; is_fwy = False; is_jct = False; speed = "NORMAL"

            # Classer le noeud
            if i == sel_idx:
                pts_sel.append(pos_a)
            elif is_ped:
                if props.show_ped: pts_ped.append(pos_a)
            else:
                if props.show_vehicle: pts_veh.append(pos_a)

            # Junction overlay (rectangle violet)
            if is_jct and props.show_junctions:
                pts_jct.append(pos_a)
                r = 6.0; x, y, z = pos_a
                # Quad violet
                tris_jct.extend([
                    (x-r,y-r,z),(x+r,y-r,z),(x+r,y+r,z),
                    (x-r,y-r,z),(x+r,y+r,z),(x-r,y+r,z),
                ])

            if not props.show_links: continue

            for lk in node.links:
                key_b = (lk.to_area_id, lk.to_node_id)
                if key_b not in node_pos: continue
                pos_b = node_pos[key_b]

                try:
                    fwd_lanes   = max(1, lk.flags2.forward_lanes)
                    back_lanes  = lk.flags2.back_lanes
                    is_dead     = lk.flags1.dead_end
                    is_shortcut = lk.flags2.shortcut
                    is_no_nav   = lk.flags2.dont_use_for_navigation
                    is_narrow   = lk.flags1.narrow_road
                except Exception:
                    fwd_lanes=1; back_lanes=0; is_dead=False
                    is_shortcut=False; is_no_nav=False; is_narrow=False

                is_lk_ped  = is_ped or node_ped.get(key_b, False)
                is_lk_fwy  = is_fwy or node_free.get(key_b, False)
                try:
                    is_parking = node.flags1.special_type == "PARKING"
                except Exception:
                    is_parking = False

                # ── OVERLAYS DE VOIES ───────────────────────────────────────
                if not is_lk_ped and props.show_vehicle:
                    lane_w = LANE_WIDTH * (0.6 if is_narrow else 1.0)

                    # Forward lanes — bande verte centrée à +offset
                    fwd_half = fwd_lanes * lane_w * 0.5
                    fwd_off  = fwd_half   # décalage positif
                    tris_fwd.extend(_lane_quad(pos_a, pos_b, fwd_off, fwd_half))

                    # Back lanes — bande rouge de l'autre côté
                    if back_lanes > 0:
                        bk_half = back_lanes * lane_w * 0.5
                        bk_off  = -bk_half
                        tris_back.extend(_lane_quad(pos_a, pos_b, bk_off, bk_half))

                # ── LIGNES DE LIENS ─────────────────────────────────────────
                pair = [pos_a, pos_b]
                if is_lk_ped or is_no_nav:
                    lines_ped_lk.extend(pair)
                elif is_dead:
                    lines_dead.extend(pair)
                elif is_parking:
                    lines_parking.extend(pair)
                elif is_lk_fwy:
                    lines_freeway.extend(pair)
                elif is_shortcut:
                    lines_shortcut.extend(pair)
                elif speed == "SLOW":
                    lines_slow.extend(pair)
                else:
                    lines_veh.extend(pair)

                # ── FLÈCHES DE DIRECTION ────────────────────────────────────
                if not is_lk_ped:
                    arrows.extend(_arrows_along(pos_a, pos_b, spacing=7.0, size=1.8))

        # ── DESSIN ─────────────────────────────────────────────────────────
        # 1. Overlays de voies (transparents, en premier)
        if tris_jct:   _batch_tris(shader, tris_jct,  C_JUNCTION)
        if tris_back:  _batch_tris(shader, tris_back, C_BACK_LANE)
        if tris_fwd:   _batch_tris(shader, tris_fwd,  C_FWD_LANE)

        # 2. Lignes de liens
        if lines_freeway:  _batch_lines(shader, lines_freeway,  C_FREEWAY,   3.0)
        if lines_veh:      _batch_lines(shader, lines_veh,      C_VEH,       1.5)
        if lines_shortcut: _batch_lines(shader, lines_shortcut, C_SHORTCUT,  1.5)
        if lines_slow:     _batch_lines(shader, lines_slow,     C_SLOW,      1.5)
        if lines_parking:  _batch_lines(shader, lines_parking,  C_PARKING,   1.5)
        if lines_ped_lk:   _batch_lines(shader, lines_ped_lk,   C_PED,       1.2)
        if lines_dead:     _batch_lines(shader, lines_dead,      C_DEAD_END, 1.5)

        # 3. Flèches de direction
        if arrows:         _batch_lines(shader, arrows, C_VEH, 1.2)

        # 4. Noeuds
        if pts_ped:  _batch_pts(shader, pts_ped,  C_NODE_PED, 4.0)
        if pts_veh:  _batch_pts(shader, pts_veh,  C_NODE_VEH, 6.0)
        if pts_sel:  _batch_pts(shader, pts_sel,  C_SELECTED, 12.0)

    # ════════════════════════════════════════════════════════════════════════
    #  YMT
    # ════════════════════════════════════════════════════════════════════════
    elif active == "YMT" and gp.ymt.show_chain_edges:
        nodes = list(gp.ymt.chaining_nodes)
        lines = []
        for edge in gp.ymt.chaining_edges:
            fi, ti = edge.node_from, edge.node_to
            if 0 <= fi < len(nodes) and 0 <= ti < len(nodes):
                lines.extend([tuple(nodes[fi].position), tuple(nodes[ti].position)])
        if lines: _batch_lines(shader, lines, C_YMT_CHAIN, 2.0)

    # ════════════════════════════════════════════════════════════════════════
    #  TRAINS
    # ════════════════════════════════════════════════════════════════════════
    elif active == "TRAINS" and gp.trains.show_track:
        pts = list(gp.trains.points)
        if len(pts) >= 2:
            strip = [p.position for p in pts]
            _batch_lines_strip(shader, strip, C_TRAINS, 2.5)
        if gp.trains.show_junctions:
            jl = []
            for pt in pts:
                if pt.flag == 4:
                    x,y,z=pt.position; r=3.0
                    jl.extend([(x-r,y,z),(x+r,y,z),(x,y-r,z),(x,y+r,z)])
            if jl: _batch_lines(shader, jl, C_TRAIN_JCT, 2.0)

    # ════════════════════════════════════════════════════════════════════════
    #  YNV — Bounding Box
    # ════════════════════════════════════════════════════════════════════════
    elif active == "YNV":
        mn = gp.ynv.bb_min; mx = gp.ynv.bb_max
        if any(mn) or any(mx):
            bb = [
                (mn[0],mn[1],mn[2]),(mx[0],mn[1],mn[2]),
                (mx[0],mn[1],mn[2]),(mx[0],mx[1],mn[2]),
                (mx[0],mx[1],mn[2]),(mn[0],mx[1],mn[2]),
                (mn[0],mx[1],mn[2]),(mn[0],mn[1],mn[2]),
                (mn[0],mn[1],mx[2]),(mx[0],mn[1],mx[2]),
                (mx[0],mn[1],mx[2]),(mx[0],mx[1],mx[2]),
                (mx[0],mx[1],mx[2]),(mn[0],mx[1],mx[2]),
                (mn[0],mx[1],mx[2]),(mn[0],mn[1],mx[2]),
                (mn[0],mn[1],mn[2]),(mn[0],mn[1],mx[2]),
                (mx[0],mn[1],mn[2]),(mx[0],mn[1],mx[2]),
                (mx[0],mx[1],mn[2]),(mx[0],mx[1],mx[2]),
                (mn[0],mx[1],mn[2]),(mn[0],mx[1],mx[2]),
            ]
            _batch_lines(shader, bb, C_YNV_BB, 1.0)

    gpu.state.blend_set("NONE")
    try: gpu.state.line_width_set(1.0)
    except Exception: pass
    try: gpu.state.point_size_set(1.0)
    except Exception: pass


# ── REGISTRATION ──────────────────────────────────────────────────────────────

_click_handler = None


def register():
    global _handle, _click_handler

    bpy.utils.register_class(YND_OT_ClickSelectNode)
    bpy.utils.register_class(YND_OT_ActivateClickSelect)

    if _handle is None:
        _handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_viewport, (), "WINDOW", "POST_VIEW"
        )


def unregister():
    global _handle

    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, "WINDOW")
        _handle = None

    for cls in [YND_OT_ActivateClickSelect, YND_OT_ClickSelectNode]:
        try: bpy.utils.unregister_class(cls)
        except Exception: pass
