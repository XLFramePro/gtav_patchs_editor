"""
ops_ynv.py — NavMesh YNV complet.
Utilise les Mesh Attributes Blender (.navmesh.poly_data0/1/2) pour stocker les flags,
exactement comme la référence Sollumz. Flags/structure calqués sur navmesh_attributes.py.

Structure flags XML (6 ou 7 valeurs) :
  "f0 f1 f2 f3 centroid_x centroid_y [f4_dlc]"
  Data0 = f0 | (f1 << 8)
  Data1 = f2 | (f3 << 8)
  Data2 = f4_dlc (0 ou 1)
  centroid_x/y = calculé à l'export (compressé 0-255 relatif à la BB du polygone)

Cover Points : objets EMPTY CONE avec custom props
Nav Links : objets EMPTY SPHERE avec custom props
"""
import bpy, bmesh, math, xml.etree.ElementTree as ET
from bpy.types import Operator, Mesh
from bpy.props import StringProperty, IntProperty, FloatProperty, EnumProperty, BoolProperty
from mathutils import Vector
from .xmlio import geti, gets, seti, sets_el, setb_el, to_xml_string

COL = "GTA5_NavMesh"

# ── Constantes grille map ─────────────────────────────────────────────────────
NAVMESH_GRID_SIZE       = 100
NAVMESH_GRID_CELL_SIZE  = 150.0
NAVMESH_GRID_BOUNDS_MIN = Vector((-6000.0, -6000.0, 0.0))
NAVMESH_STANDALONE_AREA = 10000
ADJACENCY_NONE          = 0x3FFF

# ── Noms des mesh attributes ──────────────────────────────────────────────────
ATTR_POLY_D0 = ".navmesh.poly_data0"
ATTR_POLY_D1 = ".navmesh.poly_data1"
ATTR_POLY_D2 = ".navmesh.poly_data2"
ATTR_EDGE_D0 = ".navmesh.edge_data0"
ATTR_EDGE_D1 = ".navmesh.edge_data1"
ATTR_EDGE_ADJ= ".navmesh.edge_adjacent_poly"
NAVMESH_MAT  = "YNV"  # Préfixe sans '.' pour visibilité viewport Solid

# ── Palette couleurs (RGBA, alpha pour transparence) ──────────────────────────
def _mat_color(f0, f1, f2, f3):
    """Retourne RGBA pour la couleur du matériau selon les flags."""
    if f0 & 128: return (0.05, 0.20, 0.90, 0.70)   # IsWater       — bleu
    if f0 &   8: return (0.10, 0.45, 0.10, 0.80)   # InShelter     — vert foncé
    if f1 & 128: return (0.85, 0.10, 0.10, 0.75)   # Isolated      — rouge
    if f1 &  64: return (0.85, 0.45, 0.10, 0.80)   # Interior      — orange
    if f2 &   8: return (0.50, 0.28, 0.05, 0.80)   # TrainTrack    — marron
    if f2 &  16: return (0.10, 0.70, 0.92, 0.75)   # ShallowWater  — cyan
    if f0 &   4: return (0.25, 0.75, 0.25, 0.80)   # Pavement      — vert
    if f2 &   2: return (0.80, 0.78, 0.05, 0.80)   # Road          — jaune
    if f3:       return (0.70, 0.10, 0.75, 0.75)   # Cover         — violet
    if f2 &   1: return (0.10, 0.78, 0.85, 0.75)   # Spawn         — cyan-vert
    return (0.40, 0.40, 0.40, 0.65)                 # Défaut        — gris

def _mat_name(f0, f1, f2, f3):
    return f"{NAVMESH_MAT}_{f0:03d}_{f1:03d}_{f2:03d}_{f3:03d}"

def _get_or_create_mat(f0, f1, f2, f3):
    """Create or retrieve a navmesh polygon material.
    Uses use_nodes=False + diffuse_color for reliable Solid viewport colour.
    Viewport shading must be set to 'Material' color mode (default in Blender 4.x)."""
    name = _mat_name(f0, f1, f2, f3)
    mat  = bpy.data.materials.get(name)
    if mat: return mat

    c   = _mat_color(f0, f1, f2, f3)   # (r, g, b, alpha)
    mat = bpy.data.materials.new(name)
    mat.use_backface_culling = False

    # use_nodes=False → diffuse_color IS the viewport color (Solid + Material Preview)
    mat.use_nodes    = False
    mat.diffuse_color = (c[0], c[1], c[2], c[3])
    mat.roughness     = 0.80

    # Store raw flags for retrieval
    mat["ynv_f0"] = f0; mat["ynv_f1"] = f1; mat["ynv_f2"] = f2; mat["ynv_f3"] = f3
    return mat

# ── NavPolyFlags helpers ──────────────────────────────────────────────────────

def flags_to_data(f0, f1, f2, f3):
    """Convertit les 4 bytes de flags en 2 ints data (pour mesh attribute)."""
    return f0 | (f1 << 8), f2 | (f3 << 8)

def data_to_flags(data0, data1):
    """Extrait les 4 bytes depuis les 2 ints data."""
    return data0 & 0xFF, (data0 >> 8) & 0xFF, data1 & 0xFF, (data1 >> 8) & 0xFF

def compute_centroid_compressed(poly_verts):
    """Calcule le centroïde compressé (0-255) relatif à la BB du polygone."""
    if not poly_verts: return 128, 128
    xs = [v[0] for v in poly_verts]; ys = [v[1] for v in poly_verts]
    min_x, max_x = min(xs), max(xs); min_y, max_y = min(ys), max(ys)
    cx = sum(xs) / len(xs); cy = sum(ys) / len(ys)
    sx = max_x - min_x; sy = max_y - min_y
    cx_c = int((cx - min_x) / sx * 256) if sx > 0.001 else 0
    cy_c = int((cy - min_y) / sy * 256) if sy > 0.001 else 0
    return max(0, min(255, cx_c)), max(0, min(255, cy_c))

# ── Mesh attribute helpers ────────────────────────────────────────────────────

def _ensure_attrs(mesh: Mesh):
    """Crée les mesh attributes navmesh si absents (uniquement en Object Mode)."""
    if mesh.is_editmode:
        # En Edit Mode, créer via bmesh layers
        bm = bmesh.from_edit_mesh(mesh)
        for name in (ATTR_POLY_D0, ATTR_POLY_D1, ATTR_POLY_D2):
            if bm.faces.layers.int.get(name) is None:
                bm.faces.layers.int.new(name)
        bmesh.update_edit_mesh(mesh)
    else:
        for name in (ATTR_POLY_D0, ATTR_POLY_D1, ATTR_POLY_D2):
            if name not in mesh.attributes:
                mesh.attributes.new(name, "INT", "FACE")
        for name in (ATTR_EDGE_D0, ATTR_EDGE_D1, ATTR_EDGE_ADJ):
            if name not in mesh.attributes:
                mesh.attributes.new(name, "INT", "EDGE")


def _attr_data_ok(mesh: Mesh, name: str, idx: int) -> bool:
    """Vérifie que l'attribute existe et que idx est dans les bornes."""
    if name not in mesh.attributes:
        return False
    data = mesh.attributes[name].data
    return len(data) > idx


def _set_poly_flags(mesh: Mesh, poly_idx: int, f0, f1, f2, f3, f4=0):
    """Écrit les flags sur un polygone. Gère Edit Mode et Object Mode."""
    d0, d1 = flags_to_data(f0, f1, f2, f3)
    if mesh.is_editmode:
        # En Edit Mode : utiliser bmesh layers
        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()
        if poly_idx >= len(bm.faces):
            return
        l0 = bm.faces.layers.int.get(ATTR_POLY_D0)
        l1 = bm.faces.layers.int.get(ATTR_POLY_D1)
        l2 = bm.faces.layers.int.get(ATTR_POLY_D2)
        if l0 is None: l0 = bm.faces.layers.int.new(ATTR_POLY_D0)
        if l1 is None: l1 = bm.faces.layers.int.new(ATTR_POLY_D1)
        if l2 is None: l2 = bm.faces.layers.int.new(ATTR_POLY_D2)
        bm.faces[poly_idx][l0] = d0
        bm.faces[poly_idx][l1] = d1
        bm.faces[poly_idx][l2] = f4
        bmesh.update_edit_mesh(mesh)
    else:
        # En Object Mode : utiliser mesh.attributes
        if _attr_data_ok(mesh, ATTR_POLY_D0, poly_idx):
            mesh.attributes[ATTR_POLY_D0].data[poly_idx].value = d0
        if _attr_data_ok(mesh, ATTR_POLY_D1, poly_idx):
            mesh.attributes[ATTR_POLY_D1].data[poly_idx].value = d1
        if _attr_data_ok(mesh, ATTR_POLY_D2, poly_idx):
            mesh.attributes[ATTR_POLY_D2].data[poly_idx].value = f4


def _get_poly_flags(mesh: Mesh, poly_idx: int):
    """Lit les flags d'un polygone. Gère Edit Mode et Object Mode."""
    if mesh.is_editmode:
        # En Edit Mode : lire depuis bmesh layers
        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()
        if poly_idx >= len(bm.faces):
            return 0, 0, 0, 0, 0
        l0 = bm.faces.layers.int.get(ATTR_POLY_D0)
        l1 = bm.faces.layers.int.get(ATTR_POLY_D1)
        l2 = bm.faces.layers.int.get(ATTR_POLY_D2)
        d0 = bm.faces[poly_idx][l0] if l0 else 0
        d1 = bm.faces[poly_idx][l1] if l1 else 0
        f4 = bm.faces[poly_idx][l2] if l2 else 0
    else:
        # En Object Mode : lire depuis mesh.attributes
        if not _attr_data_ok(mesh, ATTR_POLY_D0, poly_idx):
            return 0, 0, 0, 0, 0
        d0 = mesh.attributes[ATTR_POLY_D0].data[poly_idx].value
        d1 = mesh.attributes[ATTR_POLY_D1].data[poly_idx].value if _attr_data_ok(mesh, ATTR_POLY_D1, poly_idx) else 0
        f4 = mesh.attributes[ATTR_POLY_D2].data[poly_idx].value if _attr_data_ok(mesh, ATTR_POLY_D2, poly_idx) else 0

    f0, f1, f2, f3 = data_to_flags(d0, d1)
    return f0, f1, f2, f3, f4


def _get_poly_flags_from_mat(mesh: Mesh, poly_idx: int):
    """Fallback : lit les flags depuis le matériau si les attributes ne sont pas disponibles."""
    if poly_idx >= len(mesh.polygons):
        return 0, 0, 0, 0, 0
    mi  = mesh.polygons[poly_idx].material_index
    mat = mesh.materials[mi] if mi < len(mesh.materials) else None
    if mat is None:
        return 0, 0, 0, 0, 0
    return (int(mat.get("ynv_f0", 0)), int(mat.get("ynv_f1", 0)),
            int(mat.get("ynv_f2", 0)), int(mat.get("ynv_f3", 0)), 0)


def _get_poly_flags_safe(mesh: Mesh, poly_idx: int):
    """Lit les flags avec fallback sur le matériau si les attributes sont vides."""
    f = _get_poly_flags(mesh, poly_idx)
    if all(v == 0 for v in f) and len(mesh.materials) > 0:
        return _get_poly_flags_from_mat(mesh, poly_idx)
    return f


def _set_edge_adj(mesh: Mesh, edge_idx: int, area_id: int, poly_idx: int):
    val = (area_id & 0xFFFF) | ((poly_idx & 0xFFFF) << 16)
    if _attr_data_ok(mesh, ATTR_EDGE_ADJ, edge_idx):
        mesh.attributes[ATTR_EDGE_ADJ].data[edge_idx].value = val

# ── Collection helpers ────────────────────────────────────────────────────────

def _col():
    c = bpy.data.collections.get(COL)
    if not c:
        c = bpy.data.collections.new(COL)
        bpy.context.scene.collection.children.link(c)
    return c

def _link(obj, col):
    for c in obj.users_collection: c.objects.unlink(obj)
    col.objects.link(obj)

def _clear():
    col = bpy.data.collections.get(COL)
    if col:
        for o in list(col.objects): bpy.data.objects.remove(o, do_unlink=True)

# ── Grille map ────────────────────────────────────────────────────────────────

def _cell_from_name(name: str):
    """Extrait (x, y) depuis un nom type 'navmesh[120][87]'."""
    import re
    m = re.search(r'\[(\d+)\]\[(\d+)\]', name)
    if m: return int(m.group(1)) // 3, int(m.group(2)) // 3
    return -1, -1

def _cell_bounds(x, y):
    cell_min = NAVMESH_GRID_BOUNDS_MIN + Vector((x, y, 0.0)) * NAVMESH_GRID_CELL_SIZE
    cell_max = cell_min + Vector((NAVMESH_GRID_CELL_SIZE, NAVMESH_GRID_CELL_SIZE, 0.0))
    return cell_min, cell_max

def _cell_area_id(x, y):
    return y * NAVMESH_GRID_SIZE + x

# ── Parse XML ─────────────────────────────────────────────────────────────────

def _parse(filepath, props):
    props.portals.clear(); props.nav_points.clear()
    try:
        root = ET.parse(filepath).getroot()
    except Exception as e:
        return False, str(e), []
    if root.tag != "NavMesh":
        return False, f"Tag attendu NavMesh, trouvé {root.tag}", []

    cf = root.find("ContentFlags")
    props.content_flags = (cf.text or "").strip() if cf is not None else "Polygons, Portals"
    props.area_id = geti(root, "AreaID", 0)
    for tag, attr in (("BBMin","bb_min"),("BBMax","bb_max")):
        el = root.find(tag)
        if el is not None:
            setattr(props, attr, (float(el.get("x",0)), float(el.get("y",0)), float(el.get("z",0))))

    polys = []
    for item in (root.find("Polygons") or []):
        fe = item.find("Flags")
        fs = (fe.text or "0 0 0 0 0 0").strip() if fe else "0 0 0 0 0 0"
        parts = fs.split()
        while len(parts) < 7: parts.append("0")
        f0,f1,f2,f3 = int(parts[0]),int(parts[1]),int(parts[2]),int(parts[3])
        cx,cy,f4 = int(parts[4]),int(parts[5]),int(parts[6])

        verts = []
        ve = item.find("Vertices")
        if ve is not None and ve.text:
            for line in ve.text.strip().split("\n"):
                p = [x.strip().rstrip(',') for x in line.strip().split()]
                if len(p) >= 3:
                    try: verts.append((float(p[0]), float(p[1]), float(p[2])))
                    except ValueError: pass

        edges = []
        ee = item.find("Edges")
        if ee is not None and ee.text:
            for line in ee.text.strip().split("\n"):
                line = line.strip()
                if not line: continue
                # format: "area:poly, area:poly"
                parts_e = line.replace(",", " ").split()
                if len(parts_e) >= 1:
                    try:
                        ap = parts_e[0].split(":")
                        area = int(ap[0]) if len(ap)>0 else props.area_id
                        pidx = int(ap[1]) if len(ap)>1 else 0
                        edges.append((area, pidx))
                    except (ValueError, IndexError):
                        edges.append((props.area_id, 0))

        # Portails enfants du polygone (rare : indice des portails globaux qui touchent ce poly)
        poly_portals = None
        pc = item.find("Portals")
        if pc is not None and pc.text and pc.text.strip():
            poly_portals = pc.text.strip()

        polys.append({"f0":f0,"f1":f1,"f2":f2,"f3":f3,"cx":cx,"cy":cy,"f4":f4,
                      "verts":verts,"edges":edges,"poly_portals":poly_portals})

    # Portails (links dans la référence)
    for item in (root.find("Portals") or []):
        p = props.portals.add()
        t = item.find("Type");     p.portal_type = int(t.get("value",1)) if t else 1
        a = item.find("Angle");    p.angle = float(a.get("value",0)) if a else 0.0
        pf = item.find("PolyFrom");p.poly_from = int(pf.get("value",0)) if pf else 0
        pt = item.find("PolyTo");  p.poly_to   = int(pt.get("value",0)) if pt else 0
        pf2=item.find("PositionFrom")
        if pf2 is not None: p.pos_from=(float(pf2.get("x",0)),float(pf2.get("y",0)),float(pf2.get("z",0)))
        pt2=item.find("PositionTo")
        if pt2 is not None: p.pos_to  =(float(pt2.get("x",0)),float(pt2.get("y",0)),float(pt2.get("z",0)))

    # Nav Points (cover points dans la référence)
    for item in (root.find("Points") or []):
        np = props.nav_points.add()
        t   = item.find("Type");  np.point_type = str(int(t.get("value",0))) if t else "0"
        a   = item.find("Angle"); np.angle = float(a.get("value",0)) if a else 0.0
        pos = item.find("Position")
        if pos is not None: np.position=(float(pos.get("x",0)),float(pos.get("y",0)),float(pos.get("z",0)))

    props.stat_polys   = len(polys)
    props.stat_portals = len(props.portals)
    props.stat_navpts  = len(props.nav_points)
    return True, "OK", polys

# ── Build Blender mesh avec mesh attributes ───────────────────────────────────

def _build_mesh(polys, props):
    """Construit un mesh Blender avec mesh attributes navmesh."""
    # Verts non partagés (référence: chaque polygone a ses propres vertices)
    verts_all = []; faces_all = []; idx = 0
    for poly in polys:
        n = len(poly["verts"])
        if n < 3: continue
        for v in poly["verts"]: verts_all.append(v)
        faces_all.append(list(range(idx, idx + n)))
        idx += n

    mesh = bpy.data.meshes.new(f"YNV_{props.area_id}_Mesh")
    mesh.from_pydata(verts_all, [], faces_all)
    mesh.update()

    # Créer les attributes APRES from_pydata pour qu'ils aient la bonne taille
    for name in (ATTR_POLY_D0, ATTR_POLY_D1, ATTR_POLY_D2):
        if name not in mesh.attributes:
            mesh.attributes.new(name, "INT", "FACE")
    for name in (ATTR_EDGE_D0, ATTR_EDGE_D1, ATTR_EDGE_ADJ):
        if name not in mesh.attributes:
            mesh.attributes.new(name, "INT", "EDGE")

    # Precompute cumulative vertex counts for O(n) edge index lookup
    cumsum_verts = []
    total = 0
    for poly in polys:
        cumsum_verts.append(total)
        if len(poly["verts"]) >= 3:
            total += len(poly["verts"])
        # else: won't create a face, but need placeholder
    # Now cumsum_verts[face_i] = starting edge index for that face

    # Matériaux et flags
    mat_key_map = {}
    face_i = 0
    for poly in polys:
        if len(poly["verts"]) < 3: continue
        f0,f1,f2,f3,f4 = poly["f0"],poly["f1"],poly["f2"],poly["f3"],poly["f4"]

        # Mesh attribute (stockage propre)
        _set_poly_flags(mesh, face_i, f0, f1, f2, f3, f4)

        # Matériau (affichage couleur)
        key = (f0, f1, f2, f3)
        if key not in mat_key_map:
            mat = _get_or_create_mat(f0, f1, f2, f3)
            mesh.materials.append(mat)
            mat_key_map[key] = len(mesh.materials) - 1
        mesh.polygons[face_i].material_index = mat_key_map[key]

        # Edge adjacency (uses precomputed cumsum for O(n) performance)
        edges_list = poly.get("edges", [])
        base_edge = cumsum_verts[face_i]
        for vi in range(len(poly["verts"])):
            global_edge_idx = base_edge + vi
            if vi < len(edges_list) and global_edge_idx < len(mesh.edges):
                area, pidx = edges_list[vi]
                _set_edge_adj(mesh, global_edge_idx, area, pidx)

        face_i += 1

    # Obj Blender
    obj = bpy.data.objects.new(f"YNV_{props.area_id}_Mesh", mesh)
    obj["ynv_type"]    = "poly_mesh"
    obj["ynv_area_id"] = props.area_id
    props.stat_mats    = len([m for m in bpy.data.materials if m.name.startswith(NAVMESH_MAT)])
    # Ensure mesh is fully updated for correct material display
    mesh.update()
    mesh.validate()

    # Stocker le mapping {poly_index: portals_text} pour les polygones avec portails enfants
    import json as _json
    _poly_portals = {}
    _face_i = 0
    for poly_data in polys:
        if len(poly_data["verts"]) < 3: continue
        if poly_data.get("poly_portals"):
            _poly_portals[str(_face_i)] = poly_data["poly_portals"]
        _face_i += 1
    if _poly_portals:
        obj["ynv_poly_portals"] = _json.dumps(_poly_portals)

    return obj

# ── Build Blender cover points et links ──────────────────────────────────────

def _build_cover_points(props, parent, col):
    """Crée les objets EMPTY CONE pour les cover points."""
    cp_root = bpy.data.objects.new("YNV_CoverPoints", None)
    cp_root.empty_display_type = "PLAIN_AXES"; cp_root.empty_display_size = 0.1
    cp_root["ynv_type"] = "cover_root"; cp_root.parent = parent; _link(cp_root, col)
    for i, np in enumerate(props.nav_points):
        obj = bpy.data.objects.new(f"YNV_Cover{i}_T{np.point_type}", None)
        obj.empty_display_type = "CONE"; obj.empty_display_size = 0.5
        obj.location = np.position; obj.rotation_euler = (0, 0, math.pi + np.angle)
        obj.lock_rotation = (True, True, False)
        obj["ynv_type"]   = "cover_point"
        obj["cp_idx"]     = i
        obj["cp_type"]    = int(np.point_type)
        obj["cp_disabled"]= False
        obj.parent = cp_root; _link(obj, col)

def _build_links(props, parent, col):
    """Crée les objets EMPTY SPHERE pour les nav links (portails)."""
    lk_root = bpy.data.objects.new("YNV_Links", None)
    lk_root.empty_display_type = "PLAIN_AXES"; lk_root.empty_display_size = 0.1
    lk_root["ynv_type"] = "links_root"; lk_root.parent = parent; _link(lk_root, col)
    for i, p in enumerate(props.portals):
        from_obj = bpy.data.objects.new(f"YNV_Link{i}", None)
        from_obj.empty_display_type = "SPHERE"; from_obj.empty_display_size = 0.65
        from_obj.location = p.pos_from; from_obj.rotation_euler = (0, 0, p.angle)
        from_obj["ynv_type"]   = "nav_link"
        from_obj["link_idx"]   = i
        from_obj["link_type"]  = p.portal_type  # 1=ClimbLadder, 2=DescendLadder, 3=ClimbObject
        from_obj["poly_from"]  = p.poly_from
        from_obj["poly_to"]    = p.poly_to
        from_obj.parent = lk_root; _link(from_obj, col)
        to_obj = bpy.data.objects.new(f"YNV_Link{i}.target", None)
        to_obj.empty_display_type = "SPHERE"; to_obj.empty_display_size = 0.45
        to_obj.location = p.pos_to - Vector(p.pos_from)
        to_obj["ynv_type"] = "nav_link_target"; to_obj.parent = from_obj; _link(to_obj, col)

# ── Export XML ────────────────────────────────────────────────────────────────

def _export(context, props):
    root = ET.Element("NavMesh")
    ET.SubElement(root,"ContentFlags").text = props.content_flags
    seti(root,"AreaID",props.area_id)
    for tag,v in (("BBMin",props.bb_min),("BBMax",props.bb_max),
                  ("BBSize",(props.bb_max[0]-props.bb_min[0],props.bb_max[1]-props.bb_min[1],props.bb_max[2]-props.bb_min[2]))):
        el=ET.SubElement(root,tag); el.set("x",f"{v[0]:.5g}"); el.set("y",f"{v[1]:.5g}"); el.set("z",f"{v[2]:.7g}")

    # Sync positions et flags depuis le mesh
    poly_obj = next((o for o in context.scene.objects if o.get("ynv_type")=="poly_mesh"),None)
    polys_el = ET.SubElement(root,"Polygons")
    if poly_obj and poly_obj.type == "MESH":
        mesh = poly_obj.data
        # Charger le mapping poly_portals (polygones avec <Portals> enfant)
        import json as _json_exp
        _poly_portals_raw = poly_obj.get("ynv_poly_portals", "")
        try:
            _poly_portals = _json_exp.loads(_poly_portals_raw) if _poly_portals_raw else {}
        except Exception:
            _poly_portals = {}
        for poly in mesh.polygons:
            # Lire via attributes si disponibles, sinon via matériau
            f0,f1,f2,f3,f4 = _get_poly_flags_safe(mesh, poly.index)

            verts_py = [mesh.vertices[vi].co for vi in poly.vertices]
            cx, cy = compute_centroid_compressed([(v.x,v.y,v.z) for v in verts_py])

            item = ET.SubElement(polys_el,"Item")
            flags_str = f"{f0} {f1} {f2} {f3} {cx} {cy}"
            if f4: flags_str += f" {f4}"
            ET.SubElement(item,"Flags").text = flags_str

            ve = ET.SubElement(item,"Vertices")
            lines = [f"    {v.x:.7g}, {v.y:.7g}, {v.z:.7g}" for v in verts_py]
            ve.text = "\n" + "\n".join(lines) + "\n   "

            ee = ET.SubElement(item,"Edges")
            has_edge_attrs = ATTR_EDGE_ADJ in mesh.attributes
            edge_lines = []
            for vi in poly.vertices:
                if has_edge_attrs and vi < len(mesh.attributes[ATTR_EDGE_ADJ].data):
                    adj = mesh.attributes[ATTR_EDGE_ADJ].data[vi].value
                    area = adj & 0xFFFF; pidx = (adj >> 16) & 0xFFFF
                else:
                    area = props.area_id; pidx = 0
                edge_lines.append(f"    {area}:{pidx}, {area}:{pidx}")
            ee.text = "\n" + "\n".join(edge_lines) + "\n   "

            # Portails enfants du polygone (préservés depuis l'import)
            if _poly_portals and str(poly.index) in _poly_portals:
                pt_el = ET.SubElement(item, "Portals")
                pt_el.text = _poly_portals[str(poly.index)]

    # Portails (nav links)
    portals_el = ET.SubElement(root,"Portals")
    # Sync depuis objets
    for obj in context.scene.objects:
        if obj.get("ynv_type") == "nav_link":
            idx = obj.get("link_idx",-1)
            if 0 <= idx < len(props.portals):
                p = props.portals[idx]
                p.pos_from = tuple(obj.location)
                p.angle    = obj.rotation_euler.z
                p.portal_type = obj.get("link_type", 1)
                p.poly_from   = obj.get("poly_from",  0)
                p.poly_to     = obj.get("poly_to",    0)
                for child in obj.children:
                    if child.get("ynv_type") == "nav_link_target":
                        p.pos_to = tuple(obj.location + child.location)
    for p in props.portals:
        item = ET.SubElement(portals_el,"Item")
        ET.SubElement(item,"Type").set("value", str(p.portal_type))
        ET.SubElement(item,"Angle").set("value", f"{p.angle:.7g}")
        ET.SubElement(item,"PolyFrom").set("value", str(p.poly_from))
        ET.SubElement(item,"PolyTo").set("value",   str(p.poly_to))
        for tag,pos in (("PositionFrom",p.pos_from),("PositionTo",p.pos_to)):
            el=ET.SubElement(item,tag); el.set("x",f"{pos[0]:.7g}"); el.set("y",f"{pos[1]:.7g}"); el.set("z",f"{pos[2]:.7g}")

    # Cover Points
    pts_el = ET.SubElement(root,"Points")
    for obj in context.scene.objects:
        if obj.get("ynv_type") == "cover_point":
            idx = obj.get("cp_idx",-1)
            if 0 <= idx < len(props.nav_points):
                np = props.nav_points[idx]
                np.position  = tuple(obj.location)
                np.angle     = obj.rotation_euler.z - math.pi
                np.point_type= str(obj.get("cp_type", 0))
    for np in props.nav_points:
        item = ET.SubElement(pts_el,"Item")
        ET.SubElement(item,"Type").set("value", str(np.point_type))
        ET.SubElement(item,"Angle").set("value", f"{np.angle:.7g}")
        pos=ET.SubElement(item,"Position")
        pos.set("x",f"{np.position[0]:.7g}"); pos.set("y",f"{np.position[1]:.7g}"); pos.set("z",f"{np.position[2]:.7g}")
    return to_xml_string(root)

# ── Lecture/application flags depuis Edit Mode ────────────────────────────────

def _read_active_face_flags(mesh, props):
    """Lit les flags de la face active/sélectionnée et les met dans props.edit_flags.
    Fonctionne en Edit Mode et Object Mode. bm.faces.active peut être None en Blender 4.5."""
    if mesh.is_editmode:
        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()

        # Chercher la face active ou la première sélectionnée
        face_idx = None
        if bm.faces.active is not None:
            face_idx = bm.faces.active.index
        else:
            # Parcourir select_history ou la première face sélectionnée
            if hasattr(bm, "select_history"):
                for elem in reversed(list(bm.select_history)):
                    if hasattr(elem, "index") and hasattr(elem, "normal"):
                        face_idx = elem.index
                        break
            if face_idx is None:
                for f in bm.faces:
                    if f.select:
                        face_idx = f.index
                        break

        if face_idx is None:
            return False, "Aucune face sélectionnée.", -1

        ok = _read_active_face_flags_by_idx(mesh, bm, face_idx, props)
        if ok:
            f0,f1,f2,f3,f4 = _get_poly_flags_safe(mesh, face_idx)
            return True, f"Face {face_idx}: [{f0} {f1} {f2} {f3}]", face_idx
        return False, "Échec lecture flags.", -1
    else:
        face_idx = mesh.polygons.active
        if face_idx < 0:
            return False, "Aucun polygone actif.", -1
        f0,f1,f2,f3,f4 = _get_poly_flags_safe(mesh, face_idx)
        props.edit_flags.from_str(f"{f0} {f1} {f2} {f3} 0 0 {f4}")
        return True, f"Face {face_idx}: [{f0} {f1} {f2} {f3}]", face_idx


def _get_active_poly_flags(context, props):
    obj = context.active_object
    if not obj or obj.type != "MESH" or obj.get("ynv_type") != "poly_mesh":
        return False, "Activer le mesh YNV."
    if obj.mode != "EDIT":
        return False, "Passer en Edit Mode et sélectionner une face."
    ok, msg, _ = _read_active_face_flags(obj.data, props)
    return ok, msg


def _apply_flags_to_selection(context, props):
    obj = context.active_object
    if not obj or obj.get("ynv_type") != "poly_mesh" or obj.mode != "EDIT":
        return False, "Sélectionner des faces en Edit Mode."
    mesh = obj.data
    _ensure_attrs(mesh)
    fs    = props.edit_flags.to_str()
    parts = [int(x) for x in fs.split()]
    f0, f1, f2, f3 = parts[:4]
    f4 = parts[6] if len(parts) > 6 else 0

    mat = _get_or_create_mat(f0, f1, f2, f3)
    if mat not in list(mesh.materials):
        mesh.materials.append(mat)
    mi = list(mesh.materials).index(mat)

    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()

    # Préparer les bmesh layers (créer si absent)
    l0 = bm.faces.layers.int.get(ATTR_POLY_D0) or bm.faces.layers.int.new(ATTR_POLY_D0)
    l1 = bm.faces.layers.int.get(ATTR_POLY_D1) or bm.faces.layers.int.new(ATTR_POLY_D1)
    l2 = bm.faces.layers.int.get(ATTR_POLY_D2) or bm.faces.layers.int.new(ATTR_POLY_D2)

    d0, d1 = flags_to_data(f0, f1, f2, f3)
    count = 0
    for face in bm.faces:
        if face.select:
            face.material_index = mi
            face[l0] = d0
            face[l1] = d1
            face[l2] = f4
            count += 1
    bmesh.update_edit_mesh(mesh)

    # Forcer le redraw du panneau pour afficher les nouveaux flags
    for area in bpy.context.screen.areas:
        if area.type in ("VIEW_3D", "PROPERTIES"):
            area.tag_redraw()

    return True, f"{count} polygone(s) mis à jour → [{f0} {f1} {f2} {f3}]"


# ── Surveillance auto de la face active (lecture des flags en temps réel) ─────

_active_face_owner = object()
_last_active_face  = {"obj": None, "face": -1}


def _read_active_face_flags_by_idx(mesh, bm, face_idx, props):
    """Lit les flags d'une face (par son index bmesh) et met à jour props.edit_flags."""
    if face_idx < 0 or face_idx >= len(bm.faces):
        return False

    # Lire depuis bmesh layers (toujours disponible en Edit Mode)
    l0 = bm.faces.layers.int.get(ATTR_POLY_D0)
    l1 = bm.faces.layers.int.get(ATTR_POLY_D1)
    l2 = bm.faces.layers.int.get(ATTR_POLY_D2)

    if l0 is not None and l1 is not None:
        face = bm.faces[face_idx]
        d0 = face[l0]; d1 = face[l1]
        f4 = face[l2] if l2 else 0
        f0, f1, f2, f3 = data_to_flags(d0, d1)
    else:
        # Fallback : lire depuis le matériau
        f0,f1,f2,f3,f4 = _get_poly_flags_from_mat(mesh, face_idx)

    props.edit_flags.from_str(f"{f0} {f1} {f2} {f3} 0 0 {f4}")
    return True


def _on_edit_mode_change():
    """Timer — lit les flags de la face active ou sélectionnée automatiquement.
    Fonctionne même si bm.faces.active est None (Blender 4.5 : active ≠ selected)."""
    ctx = bpy.context
    if not hasattr(ctx, "scene") or not hasattr(ctx.scene, "gta5pe"): return
    if ctx.scene.gta5pe.tab != "YNV": return

    obj = ctx.active_object
    if not obj or obj.type != "MESH" or obj.get("ynv_type") != "poly_mesh": return
    if obj.mode != "EDIT": return

    mesh = obj.data
    try:
        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()

        # Stratégie 1 : face active (bm.faces.active)
        face_idx = None
        if bm.faces.active is not None:
            face_idx = bm.faces.active.index
        else:
            # Stratégie 2 : dernière face sélectionnée (select_history)
            if hasattr(bm, "select_history") and bm.select_history:
                last = bm.select_history[-1]
                if hasattr(last, "index"):
                    face_idx = last.index
            # Stratégie 3 : première face sélectionnée dans la liste
            if face_idx is None:
                for f in bm.faces:
                    if f.select:
                        face_idx = f.index
                        break

        if face_idx is None: return

        # Ne relire que si la face a changé
        cur_key = (id(obj), face_idx)
        if _last_active_face.get("key") == cur_key: return
        _last_active_face["key"] = cur_key

        props = ctx.scene.gta5pe.ynv
        _read_active_face_flags_by_idx(mesh, bm, face_idx, props)

        for area in ctx.screen.areas:
            if area.type in ("VIEW_3D", "PROPERTIES", "NLA_EDITOR"):
                area.tag_redraw()
    except Exception:
        pass  # Mesh en cours de modification — ignorer


def _register_face_tracking():
    """Enregistre le msgbus pour détecter les changements de sélection en Edit Mode."""
    # Blender msgbus sur la sélection de l'objet actif
    bpy.msgbus.subscribe_rna(
        key    = bpy.types.LayerObjects,
        owner  = _active_face_owner,
        args   = (),
        notify = _on_edit_mode_change,
        options= {"PERSISTENT"},
    )


def _unregister_face_tracking():
    bpy.msgbus.clear_by_owner(_active_face_owner)

# ── OPÉRATEURS ────────────────────────────────────────────────────────────────

class YNV_OT_Import(Operator):
    """Importe un fichier NavMesh YNV XML (flags stockés dans mesh attributes)"""
    bl_idname="gta5pe.ynv_import"; bl_label="Importer YNV"; bl_options={"REGISTER","UNDO"}
    filepath:StringProperty(subtype="FILE_PATH"); filter_glob:StringProperty(default="*.xml;*.ynv.xml",options={"HIDDEN"})
    def invoke(self,ctx,e): ctx.window_manager.fileselect_add(self); return{"RUNNING_MODAL"}
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ynv; ok,msg,polys=_parse(self.filepath,props)
        if not ok: self.report({"ERROR"},msg); return{"CANCELLED"}
        import os as _os
        filename = _os.path.basename(self.filepath)
        col_name = "GTA5PE_YNV_" + _os.path.splitext(filename)[0]
        props.filepath = self.filepath
        props["col_name"] = col_name

        # Clear previous collection for this file
        old_col = bpy.data.collections.get(col_name)
        if old_col:
            for o in list(old_col.objects): bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(old_col)

        col = bpy.data.collections.new(col_name)
        bpy.context.scene.collection.children.link(col)

        # Create root empty named after the file
        root_empty = bpy.data.objects.new(filename, None)
        root_empty.empty_display_type = "PLAIN_AXES"
        root_empty.empty_display_size = 0.01
        root_empty["ynv_type"] = "root"
        for c in root_empty.users_collection: c.objects.unlink(root_empty)
        col.objects.link(root_empty)

        if polys:
            mesh_obj = _build_mesh(polys, props)
            mesh_obj.parent = root_empty
            for c in mesh_obj.users_collection: c.objects.unlink(mesh_obj)
            col.objects.link(mesh_obj)
            _build_cover_points(props, mesh_obj, col)
            _build_links(props, mesh_obj, col)
                # Set viewport shading to Material color so polygons are visible
        for area in ctx.screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.shading.type = "SOLID"
                        space.shading.color_type = "MATERIAL"
                        break
        self.report({"INFO"},f"YNV: {props.stat_polys} polys | {props.stat_mats} mat | {props.stat_portals} links | {props.stat_navpts} covers")
        return{"FINISHED"}

class YNV_OT_New(Operator):
    """Crée une NavMesh vide avec mesh attributes"""
    bl_idname="gta5pe.ynv_new"; bl_label="Nouveau NavMesh"; bl_options={"REGISTER","UNDO"}
    area_id:IntProperty(name="Area ID",default=0,min=0)
    def invoke(self,ctx,e): return ctx.window_manager.invoke_props_dialog(self)
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ynv; props.filepath=""; props.area_id=self.area_id
        props.content_flags="Polygons, Portals"; props.portals.clear(); props.nav_points.clear()
        for s in("stat_polys","stat_portals","stat_navpts","stat_mats"): setattr(props,s,0)
        _clear(); col=_col()
        mesh=bpy.data.meshes.new(f"YNV_{self.area_id}_Mesh")
        obj=bpy.data.objects.new(f"YNV_{self.area_id}_Mesh",mesh)
        obj["ynv_type"]="poly_mesh"; obj["ynv_area_id"]=self.area_id; _link(obj,col)
        self.report({"INFO"},f"NavMesh vide créé — Area {self.area_id}"); return{"FINISHED"}

class YNV_OT_Export(Operator):
    """Exporte la NavMesh en YNV XML avec centroïdes et adjacence recalculés"""
    bl_idname="gta5pe.ynv_export"; bl_label="Exporter YNV"; bl_options={"REGISTER"}
    filepath:StringProperty(subtype="FILE_PATH"); filter_glob:StringProperty(default="*.xml",options={"HIDDEN"})
    def invoke(self,ctx,e):
        self.filepath=ctx.scene.gta5pe.ynv.filepath or "navmesh.ynv.xml"
        ctx.window_manager.fileselect_add(self); return{"RUNNING_MODAL"}
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ynv; xml=_export(ctx,props)
        try:
            with open(self.filepath,"w",encoding="utf-8") as f: f.write(xml)
        except OSError as e: self.report({"ERROR"},str(e)); return{"CANCELLED"}
        props.filepath=self.filepath; self.report({"INFO"},f"YNV exporté → {self.filepath}"); return{"FINISHED"}

class YNV_OT_ComputeBB(Operator):
    """Recalcule la bounding box depuis le mesh actif"""
    bl_idname="gta5pe.ynv_compute_bb"; bl_label="Calculer BB"; bl_options={"REGISTER","UNDO"}
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ynv
        obj=next((o for o in ctx.scene.objects if o.get("ynv_type")=="poly_mesh"),None)
        if not obj or obj.type!="MESH": self.report({"WARNING"},"Aucun mesh YNV"); return{"CANCELLED"}
        vs=[obj.matrix_world@v.co for v in obj.data.vertices]
        if not vs: return{"CANCELLED"}
        props.bb_min=(min(v.x for v in vs),min(v.y for v in vs),min(v.z for v in vs))
        props.bb_max=(max(v.x for v in vs),max(v.y for v in vs),max(v.z for v in vs))
        self.report({"INFO"},"BB calculée"); return{"FINISHED"}

class YNV_OT_ComputeBBFromGrid(Operator):
    """Calcule la BB depuis la grille map (si le nom contient [X][Y])"""
    bl_idname="gta5pe.ynv_compute_bb_grid"; bl_label="BB depuis grille"; bl_options={"REGISTER","UNDO"}
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ynv
        obj=next((o for o in ctx.scene.objects if o.get("ynv_type")=="poly_mesh"),None)
        if not obj: self.report({"WARNING"},"Aucun mesh YNV"); return{"CANCELLED"}
        cx,cy=_cell_from_name(obj.name)
        if cx<0 or cy<0:
            self.report({"WARNING"},"Nom du mesh ne contient pas [X][Y]"); return{"CANCELLED"}
        mn,mx=_cell_bounds(cx,cy)
        vz=[obj.matrix_world@v.co for v in obj.data.vertices]
        min_z=min(v.z for v in vz) if vz else 0; max_z=max(v.z for v in vz) if vz else 10
        props.bb_min=(mn.x,mn.y,min_z); props.bb_max=(mx.x,mx.y,max_z)
        props.area_id=_cell_area_id(cx,cy)
        self.report({"INFO"},f"BB grille cellule [{cx}][{cy}] → Area ID {props.area_id}"); return{"FINISHED"}

class YNV_OT_ReadFlags(Operator):
    """Lit les flags du polygone actif vers le panneau d'édition"""
    bl_idname="gta5pe.ynv_read_flags"; bl_label="Lire flags poly actif"; bl_options={"REGISTER"}
    @classmethod
    def poll(cls,ctx): o=ctx.active_object; return o and o.get("ynv_type")=="poly_mesh" and o.mode=="EDIT"
    def execute(self,ctx):
        ok,msg=_get_active_poly_flags(ctx,ctx.scene.gta5pe.ynv)
        self.report({"INFO" if ok else "WARNING"},msg); return{"FINISHED" if ok else "CANCELLED"}

class YNV_OT_ApplyPreset(Operator):
    """Applique le préset sur les polygones sélectionnés"""
    bl_idname="gta5pe.ynv_apply_preset"; bl_label="Appliquer préset"; bl_options={"REGISTER","UNDO"}
    @classmethod
    def poll(cls,ctx): o=ctx.active_object; return o and o.get("ynv_type")=="poly_mesh" and o.mode=="EDIT"
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ynv; props.edit_flags.from_preset(props.flag_preset)
        ok,msg=_apply_flags_to_selection(ctx,props)
        self.report({"INFO" if ok else "WARNING"},msg); return{"FINISHED" if ok else "CANCELLED"}

class YNV_OT_ApplyCustom(Operator):
    """Applique les flags custom sur les polygones sélectionnés"""
    bl_idname="gta5pe.ynv_apply_custom"; bl_label="Appliquer custom"; bl_options={"REGISTER","UNDO"}
    @classmethod
    def poll(cls,ctx): o=ctx.active_object; return o and o.get("ynv_type")=="poly_mesh" and o.mode=="EDIT"
    def execute(self,ctx):
        ok,msg=_apply_flags_to_selection(ctx,ctx.scene.gta5pe.ynv)
        self.report({"INFO" if ok else "WARNING"},msg); return{"FINISHED" if ok else "CANCELLED"}

class YNV_OT_SelectSimilar(Operator):
    """Sélectionne les polygones avec les mêmes flags que le polygone actif"""
    bl_idname="gta5pe.ynv_select_similar"; bl_label="Sélectionner polygones similaires"; bl_options={"REGISTER","UNDO"}
    @classmethod
    def poll(cls,ctx): o=ctx.active_object; return o and o.get("ynv_type")=="poly_mesh" and o.mode=="EDIT"
    def execute(self,ctx):
        obj=ctx.active_object; mesh=obj.data
        if ATTR_POLY_D0 not in mesh.attributes:
            self.report({"WARNING"},"Aucun mesh attribute navmesh"); return{"CANCELLED"}
        bm=bmesh.from_edit_mesh(mesh); bm.faces.ensure_lookup_table()
        if not bm.faces.active: self.report({"WARNING"},"Aucune face active"); return{"CANCELLED"}
        ref_flags=_get_poly_flags_safe(mesh, bm.faces.active.index)[:4]
        count=0
        for face in bm.faces:
            flags=_get_poly_flags_safe(mesh, face.index)[:4]
            if flags==ref_flags: face.select=True; count+=1
        bmesh.update_edit_mesh(mesh)
        self.report({"INFO"},f"{count} polygones similaires sélectionnés [{ref_flags}]"); return{"FINISHED"}

class YNV_OT_UpdateAutoFlags(Operator):
    """Recalcule IsSmall et IsLarge depuis la surface des polygones + rafraîchit les couleurs"""
    bl_idname="gta5pe.ynv_update_auto_flags"; bl_label="Recalc IsSmall/IsLarge"; bl_options={"REGISTER","UNDO"}
    @classmethod
    def poll(cls,ctx): o=ctx.active_object; return o and o.get("ynv_type")=="poly_mesh"
    def execute(self,ctx):
        obj=ctx.active_object; mesh=obj.data
        _ensure_attrs(mesh); count_s=0; count_l=0
        for poly in mesh.polygons:
            area=poly.area
            f0,f1,f2,f3,f4=_get_poly_flags_safe(mesh,poly.index)
            f0 = f0 & ~3
            if area < 2.0:  f0 |= 1; count_s+=1
            if area > 40.0: f0 |= 2; count_l+=1
            _set_poly_flags(mesh,poly.index,f0,f1,f2,f3,f4)
            mat=_get_or_create_mat(f0,f1,f2,f3)
            if mat not in list(mesh.materials): mesh.materials.append(mat)
            poly.material_index=list(mesh.materials).index(mat)
        mesh.update()
        self.report({"INFO"},f"AutoFlags: {count_s} small, {count_l} large"); return{"FINISHED"}

class YNV_OT_AddPolygon(Operator):
    """Ajoute un quad au curseur 3D"""
    bl_idname="gta5pe.ynv_add_polygon"; bl_label="Ajouter polygone"; bl_options={"REGISTER","UNDO"}
    size:FloatProperty(name="Taille",default=2.5,min=0.1)
    def execute(self,ctx):
        from .props import YNV_PRESET_VALUES
        props=ctx.scene.gta5pe.ynv; col=_col()
        obj=next((o for o in ctx.scene.objects if o.get("ynv_type")=="poly_mesh"),None)
        if obj is None:
            mesh=bpy.data.meshes.new(f"YNV_{props.area_id}_Mesh"); obj=bpy.data.objects.new(f"YNV_{props.area_id}_Mesh",mesh)
            obj["ynv_type"]="poly_mesh"; obj["ynv_area_id"]=props.area_id; _link(obj,col)
        c=ctx.scene.cursor.location; s=self.size
        bm=bmesh.new(); bm.from_mesh(obj.data)
        v=[bm.verts.new((c.x-s,c.y-s,c.z)),bm.verts.new((c.x+s,c.y-s,c.z)),bm.verts.new((c.x+s,c.y+s,c.z)),bm.verts.new((c.x-s,c.y+s,c.z))]
        bm.faces.new(v); bm.to_mesh(obj.data); bm.free(); obj.data.update()
        # S'assurer que les attributes existent (en Object Mode)
        for name in (ATTR_POLY_D0, ATTR_POLY_D1, ATTR_POLY_D2):
            if name not in obj.data.attributes:
                obj.data.attributes.new(name, "INT", "FACE")
        pv=YNV_PRESET_VALUES.get(props.flag_preset,(0,0,0,0))
        f0,f1,f2,f3=pv[0],pv[1],pv[2],pv[3]
        new_idx=len(obj.data.polygons)-1
        if _attr_data_ok(obj.data, ATTR_POLY_D0, new_idx):
            _set_poly_flags(obj.data,new_idx,f0,f1,f2,f3,0)
        mat=_get_or_create_mat(f0,f1,f2,f3)
        if mat not in list(obj.data.materials): obj.data.materials.append(mat)
        obj.data.polygons[new_idx].material_index=list(obj.data.materials).index(mat)
        props.stat_polys=len(obj.data.polygons); return{"FINISHED"}

class YNV_OT_AddPortal(Operator):
    """Ajoute un nav link (portail) au curseur"""
    bl_idname="gta5pe.ynv_add_portal"; bl_label="Ajouter Link"; bl_options={"REGISTER","UNDO"}
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ynv; p=props.portals.add(); p.portal_type=1
        c=ctx.scene.cursor.location; p.pos_from=(c.x,c.y,c.z); p.pos_to=(c.x+1,c.y,c.z+5)
        props.portal_idx=len(props.portals)-1; props.stat_portals=len(props.portals)
        col=_col(); i=props.portal_idx
        obj=bpy.data.objects.new(f"YNV_Link{i}",None); obj.empty_display_type="SPHERE"; obj.empty_display_size=0.65
        obj.location=p.pos_from; obj["ynv_type"]="nav_link"; obj["link_idx"]=i; obj["link_type"]=1; _link(obj,col)
        to_obj=bpy.data.objects.new(f"YNV_Link{i}.target",None); to_obj.empty_display_type="SPHERE"; to_obj.empty_display_size=0.45
        to_obj.location=(1,0,5); to_obj["ynv_type"]="nav_link_target"; to_obj.parent=obj; _link(to_obj,col)
        return{"FINISHED"}

class YNV_OT_RemPortal(Operator):
    """Supprime le nav link actif"""
    bl_idname="gta5pe.ynv_rem_portal"; bl_label="Supprimer Link"; bl_options={"REGISTER","UNDO"}
    @classmethod
    def poll(cls,ctx): p=ctx.scene.gta5pe.ynv; return 0<=p.portal_idx<len(p.portals)
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ynv; props.portals.remove(props.portal_idx)
        props.portal_idx=min(props.portal_idx,len(props.portals)-1); props.stat_portals=len(props.portals); return{"FINISHED"}

class YNV_OT_AddNavPt(Operator):
    """Ajoute un cover point au curseur"""
    bl_idname="gta5pe.ynv_add_navpt"; bl_label="Ajouter Cover Point"; bl_options={"REGISTER","UNDO"}
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ynv; np=props.nav_points.add()
        c=ctx.scene.cursor.location; np.position=(c.x,c.y,c.z)
        props.navpt_idx=len(props.nav_points)-1; props.stat_navpts=len(props.nav_points)
        col=_col(); i=props.navpt_idx
        obj=bpy.data.objects.new(f"YNV_Cover{i}",None); obj.empty_display_type="CONE"; obj.empty_display_size=0.5
        obj.location=(c.x,c.y,c.z); obj.lock_rotation=(True,True,False)
        obj["ynv_type"]="cover_point"; obj["cp_idx"]=i; obj["cp_type"]=0; _link(obj,col); return{"FINISHED"}

class YNV_OT_RemNavPt(Operator):
    """Supprime le cover point actif"""
    bl_idname="gta5pe.ynv_rem_navpt"; bl_label="Supprimer Cover Point"; bl_options={"REGISTER","UNDO"}
    @classmethod
    def poll(cls,ctx): p=ctx.scene.gta5pe.ynv; return 0<=p.navpt_idx<len(p.nav_points)
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ynv; props.nav_points.remove(props.navpt_idx)
        props.navpt_idx=min(props.navpt_idx,len(props.nav_points)-1); props.stat_navpts=len(props.nav_points); return{"FINISHED"}

class YNV_OT_RefreshColors(Operator):
    """Recrée tous les matériaux de couleur depuis les mesh attributes navmesh"""
    bl_idname="gta5pe.ynv_refresh_colors"; bl_label="Rafraîchir couleurs"; bl_options={"REGISTER","UNDO"}
    @classmethod
    def poll(cls,ctx): o=ctx.active_object; return o and o.get("ynv_type")=="poly_mesh"
    def execute(self,ctx):
        obj=ctx.active_object; mesh=obj.data; _ensure_attrs(mesh)
        mat_map={}; count=0
        for poly in mesh.polygons:
            f0,f1,f2,f3,_=_get_poly_flags_safe(mesh,poly.index)
            key=(f0,f1,f2,f3)
            if key not in mat_map:
                mat=_get_or_create_mat(f0,f1,f2,f3)
                if mat not in list(mesh.materials): mesh.materials.append(mat)
                mat_map[key]=list(mesh.materials).index(mat)
            poly.material_index=mat_map[key]; count+=1
        mesh.update()
        # Forcer redraw viewport
        for area in ctx.screen.areas: area.tag_redraw()
        self.report({"INFO"},f"Couleurs rafraîchies : {len(mat_map)} matériaux pour {count} polygones")
        return{"FINISHED"}


class YNV_OT_SyncEmpties(Operator):
    """Synchronise cover points et links depuis les empties de la scène"""
    bl_idname="gta5pe.ynv_sync"; bl_label="Sync depuis objets"; bl_options={"REGISTER","UNDO"}
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ynv
        props.nav_points.clear()
        for obj in sorted([o for o in ctx.scene.objects if o.get("ynv_type")=="cover_point"],
                          key=lambda o: o.get("cp_idx",0)):
            np=props.nav_points.add(); np.position=tuple(obj.location)
            np.angle=obj.rotation_euler.z - math.pi; np.point_type=str(obj.get("cp_type",0))
        props.nav_points.clear()  # rebuild from scratch via portals too
        props.stat_navpts=len(props.nav_points); props.stat_portals=len(props.portals)
        self.report({"INFO"},f"Sync: {props.stat_navpts} cover pts, {props.stat_portals} links"); return{"FINISHED"}

_CLASSES=[YNV_OT_Import,YNV_OT_New,YNV_OT_Export,
          YNV_OT_ComputeBB,YNV_OT_ComputeBBFromGrid,
          YNV_OT_ReadFlags,YNV_OT_ApplyPreset,YNV_OT_ApplyCustom,
          YNV_OT_SelectSimilar,YNV_OT_UpdateAutoFlags,YNV_OT_RefreshColors,
          YNV_OT_AddPolygon,YNV_OT_AddPortal,YNV_OT_RemPortal,
          YNV_OT_AddNavPt,YNV_OT_RemNavPt,YNV_OT_SyncEmpties]

def register():
    for cls in _CLASSES:
        try: bpy.utils.unregister_class(cls)
        except: pass
        bpy.utils.register_class(cls)
    _register_face_tracking()

def unregister():
    _unregister_face_tracking()
    for cls in reversed(_CLASSES):
        try: bpy.utils.unregister_class(cls)
        except: pass
