"""
viewport.py — GPU overlay for GTA V Pathing Editor
Draws YND path network, YNV bounding box, YMT chains, Train tracks.
Registered as a single POST_VIEW draw handler (no timer, no latency).
"""
import bpy, gpu, math
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

_handle = None

# ── Pedestrian special types (same set as props.py) ──────────────────────────
PED_TYPES = {"PED_CROSSING", "PED_ASSISTED", "PED_NOWAIT"}

# ── Colour palette (CodeWalker-inspired) ─────────────────────────────────────
C = {
    # YND lane fills
    "lane_fwd"   : (0.05, 0.72, 0.05, 0.22),   # green  – forward lanes
    "lane_bck"   : (0.72, 0.08, 0.02, 0.22),   # red    – backward lanes
    "jct_fill"   : (0.55, 0.00, 0.85, 0.14),   # purple – junction overlay
    # YND link lines
    "link_veh"   : (0.35, 0.65, 1.00, 1.0),    # blue   – vehicle road
    "link_fwy"   : (0.50, 0.15, 0.02, 1.0),    # brown  – freeway
    "link_sc"    : (0.00, 0.90, 1.00, 1.0),    # cyan   – shortcut
    "link_slow"  : (0.95, 0.95, 0.10, 1.0),    # yellow – slow zone
    "link_park"  : (0.85, 0.00, 0.85, 1.0),    # magenta– parking
    "link_ped"   : (0.90, 0.12, 0.12, 1.0),    # red    – ped / no-nav
    "link_dead"  : (1.00, 0.45, 0.00, 1.0),    # orange – dead end
    "arrow"      : (0.35, 0.65, 1.00, 0.7),    # blue   – direction arrows
    "jct_border" : (0.55, 0.00, 0.85, 0.80),   # purple – junction border
    # YND node dots
    "node_veh"   : (1.00, 1.00, 1.00, 1.0),    # white  – vehicle node
    "node_ped"   : (0.80, 0.80, 0.80, 0.9),    # grey   – ped node
    "node_sel"   : (1.00, 0.88, 0.00, 1.0),    # gold   – selected node
    # Other overlays
    "ymt"        : (1.00, 0.85, 0.15, 0.9),    # yellow – scenario chain
    "train_line" : (0.55, 0.55, 0.55, 0.9),    # grey   – train track
    "train_jct"  : (1.00, 0.40, 0.00, 1.0),    # orange – junction switch
    "ynv_bb"     : (0.20, 0.80, 1.00, 0.5),    # cyan   – navmesh BB
}

LANE_W = 1.8   # lane half-width in Blender units


# ── Low-level GPU helpers ─────────────────────────────────────────────────────

def _lw(w):
    try: gpu.state.line_width_set(w)
    except: pass

def _ps(s):
    try: gpu.state.point_size_set(s)
    except: pass

def _lines(S, verts, color, w=1.5):
    if len(verts) < 2: return
    _lw(w)
    S.uniform_float("color", color)
    batch_for_shader(S, "LINES", {"pos": verts}).draw(S)

def _pts(S, verts, color, s=6.0):
    if not verts: return
    _ps(s)
    S.uniform_float("color", color)
    batch_for_shader(S, "POINTS", {"pos": verts}).draw(S)

def _tris(S, verts, color):
    if len(verts) < 3: return
    S.uniform_float("color", color)
    batch_for_shader(S, "TRIS", {"pos": verts}).draw(S)

def _strip(S, verts, color, w=2.0):
    if len(verts) < 2: return
    _lw(w)
    S.uniform_float("color", color)
    batch_for_shader(S, "LINE_STRIP", {"pos": verts}).draw(S)


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _lane_quad(a, b, offset, half_w):
    """Two triangles forming a lane strip between points a and b."""
    ax, ay, az = a; bx, by, bz = b
    dx, dy = bx - ax, by - ay
    L = math.sqrt(dx*dx + dy*dy)
    if L < 0.01: return []
    nx, ny = -dy/L, dx/L
    ox, oy = nx*offset, ny*offset
    wx, wy = nx*half_w, ny*half_w
    v0 = (ax+ox-wx, ay+oy-wy, az); v1 = (ax+ox+wx, ay+oy+wy, az)
    v2 = (bx+ox+wx, by+oy+wy, bz); v3 = (bx+ox-wx, by+oy-wy, bz)
    return [v0, v1, v2, v0, v2, v3]

def _arrows(a, b, spacing=8.0, size=1.8):
    """Direction arrows along segment a→b."""
    ax, ay, az = a; bx, by, bz = b
    dx, dy, dz = bx-ax, by-ay, bz-az
    L = math.sqrt(dx*dx + dy*dy + dz*dz)
    if L < spacing: return []
    ux, uy = dx/L, dy/L
    nx, ny = -uy, ux
    result = []
    n = max(1, int(L / spacing))
    for i in range(1, n+1):
        t = i / (n+1)
        cx = ax + dx*t; cy = ay + dy*t; cz = az + dz*t
        s = size * 0.55
        result.extend([
            (cx - ux*s + nx*s, cy - uy*s + ny*s, cz),
            (cx, cy, cz),
            (cx - ux*s - nx*s, cy - uy*s - ny*s, cz),
            (cx, cy, cz),
        ])
    return result

def _jct_quad(cx, cy, cz, sx, sy):
    """Filled quad for junction overlay."""
    hw, hh = sx/2, sy/2
    return [
        (cx-hw, cy-hh, cz), (cx+hw, cy-hh, cz), (cx+hw, cy+hh, cz),
        (cx-hw, cy-hh, cz), (cx+hw, cy+hh, cz), (cx-hw, cy+hh, cz),
    ]

def _jct_border(cx, cy, cz, sx, sy):
    """Border lines for junction overlay."""
    hw, hh = sx/2, sy/2
    return [
        (cx-hw, cy-hh, cz), (cx+hw, cy-hh, cz),
        (cx+hw, cy-hh, cz), (cx+hw, cy+hh, cz),
        (cx+hw, cy+hh, cz), (cx-hw, cy+hh, cz),
        (cx-hw, cy+hh, cz), (cx-hw, cy-hh, cz),
    ]

def _bb_lines(mn, mx):
    """12 edges of a bounding box."""
    x0, y0, z0 = mn; x1, y1, z1 = mx
    return [
        (x0,y0,z0),(x1,y0,z0),  (x1,y0,z0),(x1,y1,z0),
        (x1,y1,z0),(x0,y1,z0),  (x0,y1,z0),(x0,y0,z0),
        (x0,y0,z1),(x1,y0,z1),  (x1,y0,z1),(x1,y1,z1),
        (x1,y1,z1),(x0,y1,z1),  (x0,y1,z1),(x0,y0,z1),
        (x0,y0,z0),(x0,y0,z1),  (x1,y0,z0),(x1,y0,z1),
        (x1,y1,z0),(x1,y1,z1),  (x0,y1,z0),(x0,y1,z1),
    ]


# ── Main draw callback ────────────────────────────────────────────────────────

def _draw():
    ctx = bpy.context
    if not hasattr(ctx, "scene") or not hasattr(ctx.scene, "gta5pe"):
        return

    gp = ctx.scene.gta5pe
    S  = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")
    S.bind()

    # ── YND ──────────────────────────────────────────────────────────────────
    if gp.tab == "YND":
        p   = gp.ynd
        sel = p.node_idx

        # Build position + flag lookup (keyed by area_id, node_id)
        pos_map  = {}
        ped_map  = {}
        fwy_map  = {}
        for nd in p.nodes:
            k = (nd.area_id, nd.node_id)
            pos_map[k]  = tuple(nd.position)
            try:
                ped_map[k] = nd.nf1.special_type in PED_TYPES
                fwy_map[k] = bool(nd.nf2.freeway)
            except Exception:
                ped_map[k] = False
                fwy_map[k] = False

        # Collect geometry
        t_fwd  = []; t_bck  = []; t_jct  = []
        l_veh  = []; l_fwy  = []; l_sc   = []; l_slow = []
        l_park = []; l_ped  = []; l_dead = []
        arrs   = []
        pv     = []; pp     = []; ps     = []
        jb     = []

        for i, nd in enumerate(p.nodes):
            pa = tuple(nd.position)
            k_a = (nd.area_id, nd.node_id)

            try:
                is_ped  = nd.nf1.special_type in PED_TYPES
                is_park = (nd.nf1.special_type == "PARKING")
                is_fwy  = bool(nd.nf2.freeway)
                is_jct  = bool(nd.nf2.junction)
                speed   = nd.nf5.speed
            except Exception:
                is_ped = is_park = is_fwy = is_jct = False
                speed = "NORMAL"

            # Node dots
            if i == sel:
                ps.append(pa)
            elif is_ped and p.show_ped:
                pp.append(pa)
            elif (not is_ped) and p.show_vehicle:
                pv.append(pa)

            # Junction overlay: find matching junction data by position proximity
            if is_jct and p.show_junctions:
                sx, sy = _find_junction_size(p, pa)
                t_jct.extend(_jct_quad(pa[0], pa[1], pa[2], sx, sy))
                jb.extend(_jct_border(pa[0], pa[1], pa[2], sx, sy))

            # Links
            if not p.show_links:
                continue

            for lk in nd.links:
                k_b = (lk.to_area_id, lk.to_node_id)
                if k_b not in pos_map:
                    continue
                pb = pos_map[k_b]

                try:
                    fwd  = max(1, lk.lf2.forward_lanes)
                    bk   = lk.lf2.back_lanes
                    dead = bool(lk.lf1.dead_end)
                    sc   = bool(lk.lf2.shortcut)
                    noN  = bool(lk.lf2.dont_use_for_navigation)
                    nr   = bool(lk.lf1.narrow_road)
                except Exception:
                    fwd = 1; bk = 0; dead = sc = noN = nr = False

                is_lk_ped = is_ped or ped_map.get(k_b, False)
                is_lk_fwy = is_fwy or fwy_map.get(k_b, False)

                # Lane fills (vehicle only)
                if (not is_lk_ped) and p.show_vehicle:
                    lw = LANE_W * (0.6 if nr else 1.0)
                    fh = fwd * lw * 0.5
                    t_fwd.extend(_lane_quad(pa, pb,  fh, fh))
                    if bk > 0:
                        bh = bk * lw * 0.5
                        t_bck.extend(_lane_quad(pa, pb, -bh, bh))

                # Link lines
                pair = [pa, pb]
                if is_lk_ped or noN:   l_ped.extend(pair)
                elif dead:              l_dead.extend(pair)
                elif is_park:           l_park.extend(pair)
                elif is_lk_fwy:        l_fwy.extend(pair)
                elif sc:               l_sc.extend(pair)
                elif speed == "SLOW":  l_slow.extend(pair)
                else:                  l_veh.extend(pair)

                if not is_lk_ped:
                    arrs.extend(_arrows(pa, pb))

        # Draw order: fills first, then lines, then dots
        if t_jct:  _tris(S,  t_jct,  C["jct_fill"])
        if t_bck:  _tris(S,  t_bck,  C["lane_bck"])
        if t_fwd:  _tris(S,  t_fwd,  C["lane_fwd"])
        if l_fwy:  _lines(S, l_fwy,  C["link_fwy"],  3.0)
        if l_veh:  _lines(S, l_veh,  C["link_veh"],  1.5)
        if l_sc:   _lines(S, l_sc,   C["link_sc"],   1.5)
        if l_slow: _lines(S, l_slow, C["link_slow"],  1.5)
        if l_park: _lines(S, l_park, C["link_park"],  1.5)
        if l_ped:  _lines(S, l_ped,  C["link_ped"],  1.2)
        if l_dead: _lines(S, l_dead, C["link_dead"],  1.5)
        if arrs:   _lines(S, arrs,   C["arrow"],      1.0)
        if jb:     _lines(S, jb,     C["jct_border"], 1.5)
        if pp:     _pts(S,   pp,     C["node_ped"],   4.0)
        if pv:     _pts(S,   pv,     C["node_veh"],   6.0)
        if ps:     _pts(S,   ps,     C["node_sel"],  12.0)

    # ── YMT ──────────────────────────────────────────────────────────────────
    elif gp.tab == "YMT" and gp.ymt.show_chain:
        nds  = list(gp.ymt.chain_nodes)
        lns  = []
        for ce in gp.ymt.chain_edges:
            fi, ti = ce.node_from, ce.node_to
            if 0 <= fi < len(nds) and 0 <= ti < len(nds):
                lns.extend([tuple(nds[fi].position), tuple(nds[ti].position)])
        if lns:
            _lines(S, lns, C["ymt"], 2.0)

    # ── TRAINS ───────────────────────────────────────────────────────────────
    elif gp.tab == "TRAINS" and gp.trains.show_track:
        pts = list(gp.trains.points)
        if len(pts) >= 2:
            _strip(S, [tuple(pt.position) for pt in pts], C["train_line"], 2.5)
        if gp.trains.show_jct:
            jl = []
            for pt in pts:
                if pt.flag == 4:
                    x, y, z = pt.position
                    r = 3.0
                    jl.extend([(x-r, y, z), (x+r, y, z), (x, y-r, z), (x, y+r, z)])
            if jl:
                _lines(S, jl, C["train_jct"], 2.0)

    # ── YNV bounding box ─────────────────────────────────────────────────────
    elif gp.tab == "YNV" and gp.ynv.show_bb:
        mn = gp.ynv.bb_min; mx = gp.ynv.bb_max
        if any(mn) or any(mx):
            _lines(S, _bb_lines(mn, mx), C["ynv_bb"], 1.0)

    gpu.state.blend_set("NONE")
    _lw(1.0)
    _ps(1.0)


def _find_junction_size(ynd_props, node_pos, threshold=15.0):
    """Find the junction size for a node by matching JunctionRef → Junction position."""
    # Match each junction via JunctionRefs proximity
    for ref in ynd_props.junction_refs:
        if ref.area_id == 0 and ref.node_id == 0:
            continue
        jct_idx = ref.junction_id
        if jct_idx < len(ynd_props.junctions):
            j = ynd_props.junctions[jct_idx]
            # Check if this ref matches the node position approximately
            # We use position proximity since we don't have direct node→ref link
            try:
                jx = float(j.pos_x); jy = float(j.pos_y)
                dx = node_pos[0] - jx; dy = node_pos[1] - jy
                dist = math.sqrt(dx*dx + dy*dy)
                if dist < threshold:
                    sx = int(j.size_x) if j.size_x else 8
                    sy = int(j.size_y) if j.size_y else 8
                    return max(4, sx), max(4, sy)
            except Exception:
                pass
    return 10, 10   # default size


def register():
    global _handle
    if _handle is None:
        _handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw, (), "WINDOW", "POST_VIEW")

def unregister():
    global _handle
    if _handle:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, "WINDOW")
        _handle = None
