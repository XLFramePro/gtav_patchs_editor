"""
operators_ynv.py — Complete NavMesh YNV.
"""

import bpy, bmesh, json, xml.etree.ElementTree as ET, math, os
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty, IntProperty, FloatProperty
from mathutils import Vector
from .xml_utils import fval, ival, sval, sub_val, sub_text, to_xml_string

YNV_COLLECTION = "YNV_NavMesh"

FLAG_PRESETS = {
    "ROAD":      (0,   0, 2, 0),
    "PAVEMENT":  (4,   0, 0, 0),
    "INTERIOR":  (0,  32, 0, 0),
    "WATER":     (128, 0, 0, 0),
    "SHALLOW":   (0,   0,16, 0),
    "TRAIN":     (0,   0, 8, 0),
    "COVER":     (0,   0, 2,63),
    "SPAWN":     (0,   0, 3, 0),
    "CUSTOM":    (0,   0, 0, 0),
}

def _flag_label_parts(b0, b1, b2, b3):
    """Returns a list of strings describing active flags."""
    parts = []
    if b0 & 128: parts.append("Water")
    if b0 & 64:  parts.append("TooSteep")
    if b0 & 8:   parts.append("Underground")
    if b0 & 4:   parts.append("Pavement")
    if b0 & 2:   parts.append("LargePoly")
    if b0 & 1:   parts.append("SmallPoly")
    if b1 & 64:  parts.append("Isolated")
    if b1 & 32:  parts.append("Interior")
    if b1 & 16:  parts.append("NearCar")
    audio = b1 & 7
    if audio:    parts.append(f"Aud{audio}")
    if b2 & 8:   parts.append("TrainTrack")
    if b2 & 16:  parts.append("Shallow")
    if b2 & 4:   parts.append("AlongEdge")
    if b2 & 2:   parts.append("Road")
    if b2 & 1:   parts.append("Spawn")
    ped = (b2 >> 5) & 7
    if ped:      parts.append(f"Ped{ped}")
    if b3:       parts.append(f"Cov{b3:02X}")
    return parts if parts else ["Default"]


def _flag_color(b0, b1, b2, b3):
    """Returns RGBA (0-1) according to surface priority."""
    if b0 & 128:            return (0.05, 0.15, 0.85, 0.85)   # Water — deep blue
    if b0 & 8:              return (0.15, 0.45, 0.15, 0.85)   # Underground — dark green
    if b1 & 32:             return (0.85, 0.45, 0.10, 0.85)   # Interior — orange
    if b1 & 64:             return (0.85, 0.10, 0.10, 0.80)   # Isolated — red
    if b2 & 8:              return (0.55, 0.35, 0.05, 0.85)   # TrainTrack — brown
    if b2 & 16:             return (0.15, 0.70, 0.90, 0.80)   # Shallow — cyan
    if (b0 & 4) and b3:     return (0.60, 0.82, 0.30, 0.85)   # Pavement+Cover — yellow-green
    if (b2 & 2) and b3:     return (0.92, 0.72, 0.08, 0.85)   # Road+Cover — amber
    if b0 & 4:              return (0.42, 0.78, 0.42, 0.85)   # Pavement — green
    if b2 & 2:              return (0.78, 0.78, 0.18, 0.85)   # Road — yellow
    if b3:                  return (0.78, 0.10, 0.78, 0.80)   # Cover-only — purple
    if b2 & 1:              return (0.18, 0.78, 0.85, 0.80)   # Spawn — teal
    return (0.50, 0.50, 0.50, 0.75)                           # Default — grey


def _mat_key(b0, b1, b2, b3):
    """Unique key for a material (bytes 0-3)."""
    return f"YNV_{b0:03d}_{b1:03d}_{b2:03d}_{b3:03d}"


def _mat_name(b0, b1, b2, b3):
    """Complete material name with readable description, max 63 chars."""
    label = "_".join(_flag_label_parts(b0, b1, b2, b3))
    base  = f"YNV_{label}"
    return base[:63]   # Blender limits names to 63 chars


def _get_or_create_material(b0, b1, b2, b3):
    """Returns (without duplicating) the material for these b0-b3 flags."""
    key  = _mat_key(b0, b1, b2, b3)
    name = _mat_name(b0, b1, b2, b3)

    # Look for existing material with name starting with key
    mat = bpy.data.materials.get(name)
    if mat is None:
        # Look by prefix in case name was truncated
        mat = next((m for m in bpy.data.materials if m.name.startswith(key)), None)

    if mat is not None:
        return mat

    # Create the material
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    out  = nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    color = _flag_color(b0, b1, b2, b3)
    bsdf.inputs["Base Color"].default_value     = color
    bsdf.inputs["Roughness"].default_value       = 0.85
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (*color[:3], 1.0)
        bsdf.inputs["Emission Strength"].default_value = 0.05

    mat.use_backface_culling = False
    if hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"

    # Set viewport color for solid mode visibility
    mat.diffuse_color = color

    # Store flags in material custom props
    mat["ynv_b0"] = b0; mat["ynv_b1"] = b1
    mat["ynv_b2"] = b2; mat["ynv_b3"] = b3

    return mat


def _parse_flags_str(flags_str):
    """Convert raw flag string to 7 bytes: b0..b6.

    CodeWalker accepts 7 bytes for YNV polygon flags.
    """
    try:
        parts = [int(x) for x in flags_str.split()]
        while len(parts) < 7:
            parts.append(0)
        return parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], parts[6]
    except Exception:
        return 0, 0, 0, 0, 0, 0, 0


# ─────────────────────────────────────────────────────────────────────────────
#  PARSE XML → python data
# ─────────────────────────────────────────────────────────────────────────────

def _parse_vertex_line(line):
    parts = line.strip().split(",")
    return tuple(float(p.strip()) for p in parts if p.strip())


def _parse_ynv_xml(filepath, props):
    props.portals.clear()
    props.nav_points.clear()
    try:
        tree = ET.parse(filepath)
    except ET.ParseError as e:
        return False, str(e), []
    root = tree.getroot()
    if root.tag != "NavMesh":
        return False, f"Expected NavMesh root, found {root.tag}", []

    cf = root.find("ContentFlags")
    props.content_flags = (cf.text or "").strip() if cf is not None else "Polygons, Portals"
    aid = root.find("AreaID")
    props.area_id = int(aid.get("value", 0)) if aid is not None else 0

    for tag, attr in [("BBMin", "bb_min"), ("BBMax", "bb_max")]:
        el = root.find(tag)
        if el is not None:
            setattr(props, attr, (float(el.get("x",0)), float(el.get("y",0)), float(el.get("z",0))))

    polygons_data = []
    polys_el = root.find("Polygons")
    if polys_el is not None:
        for item in polys_el.findall("Item"):
            flags_el = item.find("Flags")
            flags_str = (flags_el.text or "0 0 0 0 0 0").strip() if flags_el is not None else "0 0 0 0 0 0"
            verts_el  = item.find("Vertices")
            verts = []
            if verts_el is not None and verts_el.text:
                for line in verts_el.text.strip().split("\n"):
                    if line.strip():
                        parsed = _parse_vertex_line(line)
                        if len(parsed) == 3:
                            verts.append(parsed)
            edges_el = item.find("Edges")
            edges_raw = []
            if edges_el is not None and edges_el.text:
                for line in edges_el.text.strip().split("\n"):
                    if line.strip():
                        edges_raw.append(line.strip())
            edges_flags_el = item.find("EdgesFlags")
            edges_flags_raw = []
            if edges_flags_el is not None and edges_flags_el.text:
                for line in edges_flags_el.text.strip().split("\n"):
                    if line.strip():
                        edges_flags_raw.append(line.strip())

            portals_poly_el = item.find("Portals")
            portals_poly_raw = []
            if portals_poly_el is not None and portals_poly_el.text:
                for tok in portals_poly_el.text.replace("\n", " ").replace(",", " ").split():
                    try:
                        portals_poly_raw.append(int(tok))
                    except ValueError:
                        pass

            polygons_data.append({
                "flags": flags_str,
                "verts": verts,
                "edges": edges_raw,
                "edges_flags": edges_flags_raw,
                "poly_portals": portals_poly_raw,
            })

    portals_el = root.find("Portals")
    if portals_el is not None:
        for item in portals_el.findall("Item"):
            p = props.portals.add()
            t = item.find("Type");   p.portal_type = int(t.get("value",1)) if t is not None else 1
            a = item.find("Angle");  p.angle       = float(a.get("value",0)) if a is not None else 0.0
            pf_el = item.find("PolyFrom"); p.poly_from = int(pf_el.get("value",0)) if pf_el is not None else 0
            pt_el = item.find("PolyTo");   p.poly_to   = int(pt_el.get("value",0)) if pt_el is not None else 0
            pfrom = item.find("PositionFrom")
            if pfrom is not None: p.pos_from = (float(pfrom.get("x",0)), float(pfrom.get("y",0)), float(pfrom.get("z",0)))
            pto = item.find("PositionTo")
            if pto is not None:   p.pos_to   = (float(pto.get("x",0)), float(pto.get("y",0)), float(pto.get("z",0)))

    points_el = root.find("Points")
    if points_el is not None:
        for item in points_el.findall("Item"):
            np = props.nav_points.add()
            t  = item.find("Type");  np.point_type = int(t.get("value",0)) if t is not None else 0
            a  = item.find("Angle"); np.angle       = float(a.get("value",0)) if a is not None else 0.0
            pos = item.find("Position")
            if pos is not None: np.position = (float(pos.get("x",0)), float(pos.get("y",0)), float(pos.get("z",0)))

    props.stat_polygons  = len(polygons_data)
    props.stat_portals   = len(props.portals)
    props.stat_navpoints = len(props.nav_points)
    return True, "OK", polygons_data


# ─────────────────────────────────────────────────────────────────────────────
#  CONSTRUCTION DES OBJETS BLENDER
# ─────────────────────────────────────────────────────────────────────────────

def _get_or_create_col(name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def _link_obj(obj, col):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    col.objects.link(obj)


def _get_or_create_cube_mesh(name, size=0.5):
    """Create (or reuse) a simple cube mesh used by YNV markers."""
    mesh = bpy.data.meshes.get(name)
    if mesh is not None:
        return mesh

    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh


def _get_asset_path(filename):
    """Return absolute path for an addon asset file."""
    return os.path.join(os.path.dirname(__file__), "assets", filename)


def _load_marker_mesh_from_glb(cache_name):
    """Import the marker GLB once and cache its first mesh datablock.

    Returns None if the asset cannot be imported.
    """
    mesh = bpy.data.meshes.get(cache_name)
    if mesh is not None:
        return mesh

    asset_path = _get_asset_path("cube_arrow.glb")
    if not os.path.exists(asset_path):
        return None
    if not hasattr(bpy.ops.import_scene, "gltf"):
        return None

    object_names_before = {obj.name for obj in bpy.data.objects}
    collection_names_before = {col.name for col in bpy.data.collections}

    try:
        result = bpy.ops.import_scene.gltf(filepath=asset_path)
    except Exception:
        return None

    if "FINISHED" not in result:
        return None

    new_objects = [obj for obj in bpy.data.objects if obj.name not in object_names_before]
    source_obj = next((obj for obj in new_objects if obj.type == "MESH"), None)
    if source_obj is None:
        for obj in reversed(new_objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for col in list(bpy.data.collections):
            if col.name not in collection_names_before and not col.objects and not col.children:
                bpy.data.collections.remove(col)
        return None

    mesh = source_obj.data.copy()
    mesh.name = cache_name
    mesh.transform(source_obj.matrix_world)
    mesh.update()

    for obj in reversed(new_objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for col in list(bpy.data.collections):
        if col.name not in collection_names_before and not col.objects and not col.children:
            bpy.data.collections.remove(col)

    return mesh


def _get_or_create_marker_mesh(cache_name, fallback_name, fallback_size):
    """Return marker mesh and whether it already contains embedded direction."""
    mesh = _load_marker_mesh_from_glb(cache_name)
    if mesh is not None:
        return mesh, True
    return _get_or_create_cube_mesh(fallback_name, size=fallback_size), False


def _apply_sollumz_type(obj, type_name):
    """Apply Sollumz type on object when property/addon is available."""
    if not hasattr(obj, "sollum_type"):
        return False

    mapping = {
        "NAVMESH": "sollumz_navmesh",
        "NAVMESH_POLY_MESH": "sollumz_navmesh_mesh",
        "NAVMESH_PORTAL": "sollumz_navmesh_portal",
        "NAVMESH_POINT": "sollumz_navmesh_point",
    }
    candidate = mapping.get(type_name, type_name)
    try:
        obj.sollum_type = candidate
        return True
    except Exception:
        return False


def _add_direction_arrow(parent_obj, col, angle, size=0.85):
    """Attach a visual arrow empty to show direction."""
    arrow = bpy.data.objects.new(f"{parent_obj.name}_Dir", None)
    arrow.empty_display_type = "SINGLE_ARROW"
    arrow.empty_display_size = size
    arrow.location = (0.0, 0.0, 0.0)
    arrow.rotation_euler = (0.0, 0.0, angle)
    arrow["ynv_type"] = "direction_arrow"
    arrow.parent = parent_obj
    _link_obj(arrow, col)
    return arrow


def _idx_name(i):
    """Sollumz-like 1-based suffix formatting."""
    return f"{i + 1:02d}"


def _build_ynv_root(name, col):
    """Create top-level YNV root object for clean hierarchy."""
    root = bpy.data.objects.new(name, None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 1.0
    root["ynv_type"] = "root"
    _link_obj(root, col)
    _apply_sollumz_type(root, "NAVMESH")
    return root


def _build_navmesh_obj(polygons_data, area_id):
    """Builds the Blender mesh with shared materials per (b0,b1,b2,b3)."""
    vert_map    = {}
    verts_list  = []
    faces_list  = []
    # For each face: keep flags and raw edge metadata so export can preserve structure.
    face_flags  = []
    face_edges  = []
    face_edge_flags = []
    face_portals = []

    for poly in polygons_data:
        b0, b1, b2, b3, b4, b5, b6 = _parse_flags_str(poly["flags"])
        face_indices = []
        for v in poly["verts"]:
            key = (round(v[0], 4), round(v[1], 4), round(v[2], 4))
            if key not in vert_map:
                vert_map[key] = len(verts_list)
                verts_list.append(v)
            face_indices.append(vert_map[key])
        if len(face_indices) >= 3:
            faces_list.append(face_indices)
            face_flags.append((b0, b1, b2, b3, b4, b5, b6))
            face_edges.append(poly.get("edges", []))
            face_edge_flags.append(poly.get("edges_flags", []))
            face_portals.append(poly.get("poly_portals", []))

    mesh = bpy.data.meshes.new("NavMesh Poly Mesh")
    mesh.from_pydata(verts_list, [], faces_list)
    mesh.update()

    # Create/retrieve materials without duplicates per (b0,b1,b2,b3)
    # Dictionary mat_key → index in mesh.materials
    mat_index_map = {}

    for i, (b0, b1, b2, b3, b4, b5, b6) in enumerate(face_flags):
        key = _mat_key(b0, b1, b2, b3)
        if key not in mat_index_map:
            mat = _get_or_create_material(b0, b1, b2, b3)
            mesh.materials.append(mat)
            mat_index_map[key] = len(mesh.materials) - 1

    # Assign material_index to each polygon
    for i, (b0, b1, b2, b3, b4, b5, b6) in enumerate(face_flags):
        key = _mat_key(b0, b1, b2, b3)
        mesh.polygons[i].material_index = mat_index_map[key]
        # Store bytes 4-5 (internal density) in polygon custom prop if possible
        # For now, we store them in a layer via bpy if necessary — but pass

    obj = bpy.data.objects.new("NavMesh Poly Mesh", mesh)
    obj["ynv_type"]    = "poly_mesh"
    obj["ynv_area_id"] = area_id
    _apply_sollumz_type(obj, "NAVMESH_POLY_MESH")
    # Store per-face extra bytes + edge metadata for faithful XML rebuilding.
    b456_data = [(ff[4], ff[5], ff[6]) for ff in face_flags]
    obj["ynv_bytes456"] = json.dumps(b456_data)
    # Backward compatibility with older data layout.
    obj["ynv_bytes45"] = json.dumps([(ff[4], ff[5]) for ff in face_flags])
    obj["ynv_edge_lines"] = json.dumps(face_edges)
    obj["ynv_edge_flag_lines"] = json.dumps(face_edge_flags)
    obj["ynv_poly_portals"] = json.dumps(face_portals)
    return obj


def _build_portals_objs(props, col):
    root = bpy.data.objects.new("Portals", None)
    root.empty_display_type = "PLAIN_AXES"; root.empty_display_size = 0.5
    root["ynv_type"] = "portals_root"; _link_obj(root, col)

    portal_mesh, portal_has_arrow = _get_or_create_marker_mesh("YNV_CubeArrowPortalMesh", "YNV_PortalCube", 0.35)
    point_mesh, point_has_arrow = _get_or_create_marker_mesh("YNV_CubeArrowPointMesh", "YNV_PortalPointCube", 0.22)

    for i, portal in enumerate(props.portals):
        # Main portal marker at segment midpoint, oriented on Z from from->to.
        pfrom = Vector(portal.pos_from)
        pto = Vector(portal.pos_to)
        center = (pfrom + pto) * 0.5
        direction = pto - pfrom

        idx = _idx_name(i)
        portal_obj = bpy.data.objects.new(f"NavMesh Portal.{idx}", portal_mesh)
        portal_obj.location = center
        if direction.length_squared > 1e-9:
            portal_obj.rotation_euler = (0.0, 0.0, math.atan2(direction.y, direction.x))
        portal_obj["ynv_type"] = "portal"
        portal_obj["portal_index"] = i
        portal_obj["portal_type"] = portal.portal_type
        portal_obj["poly_from"] = portal.poly_from
        portal_obj["poly_to"] = portal.poly_to
        portal_obj.parent = root
        _link_obj(portal_obj, col)
        _apply_sollumz_type(portal_obj, "NAVMESH_PORTAL")
        if portal_has_arrow:
            portal_obj.scale = (1.15, 1.15, 1.15)
        else:
            _add_direction_arrow(portal_obj, col, 0.0, size=0.75)

        from_obj = bpy.data.objects.new(f"PortalFrom Point.{idx}", point_mesh)
        from_obj.location = portal.pos_from
        from_obj.rotation_euler = (0.0, 0.0, portal_obj.rotation_euler.z)
        from_obj["ynv_type"] = "portal_from"
        from_obj["portal_index"] = i
        from_obj["portal_type"] = portal.portal_type
        from_obj["poly_from"] = portal.poly_from
        from_obj["poly_to"] = portal.poly_to
        from_obj.parent = portal_obj
        _link_obj(from_obj, col)
        _apply_sollumz_type(from_obj, "NAVMESH_PORTAL")
        if not point_has_arrow:
            _add_direction_arrow(from_obj, col, 0.0, size=0.65)

        to_obj = bpy.data.objects.new(f"PortalTo Point.{idx}", point_mesh)
        to_obj.location = portal.pos_to
        to_obj.rotation_euler = (0.0, 0.0, portal_obj.rotation_euler.z + math.pi)
        to_obj["ynv_type"] = "portal_to"
        to_obj["portal_index"] = i
        to_obj["portal_type"] = portal.portal_type
        to_obj["poly_from"] = portal.poly_from
        to_obj["poly_to"] = portal.poly_to
        to_obj.parent = portal_obj
        _link_obj(to_obj, col)
        _apply_sollumz_type(to_obj, "NAVMESH_PORTAL")
        if not point_has_arrow:
            _add_direction_arrow(to_obj, col, 0.0, size=0.65)
    return root


def _build_navpoints_objs(props, col):
    root = bpy.data.objects.new("Points", None)
    root.empty_display_type = "PLAIN_AXES"; root.empty_display_size = 0.1
    root["ynv_type"] = "navpoints_root"; _link_obj(root, col)
    nav_mesh, nav_has_arrow = _get_or_create_marker_mesh("YNV_CubeArrowNavPointMesh", "YNV_NavPointCube", 0.28)

    for i, np_item in enumerate(props.nav_points):
        obj = bpy.data.objects.new(f"NavMesh Point.{_idx_name(i)}", nav_mesh)
        obj.location = np_item.position; obj.rotation_euler = (0, 0, np_item.angle)
        obj["ynv_type"] = "nav_point"; obj["point_index"] = i
        obj["point_type"] = np_item.point_type; obj["point_angle"] = np_item.angle
        obj.parent = root; _link_obj(obj, col)
        _apply_sollumz_type(obj, "NAVMESH_POINT")
        if not nav_has_arrow:
            _add_direction_arrow(obj, col, 0.0, size=0.85)
    return root


def _iter_navpoint_objects(context):
    """Return nav point empties sorted by stable point index then name."""
    nav_objs = [o for o in context.scene.objects if o.get("ynv_type") == "nav_point"]
    return sorted(nav_objs, key=lambda o: (int(o.get("point_index", 10**9)), o.name))


def _sync_navpoints_from_objects(context, props, keep_props_if_no_objects=False):
    """Sync nav_points collection from nav_point empties.

    If keep_props_if_no_objects is True and no nav_point empties exist,
    keep current props.nav_points untouched.
    Returns (count, synced_from_objects).
    """
    nav_objs = _iter_navpoint_objects(context)
    if keep_props_if_no_objects and not nav_objs:
        props.stat_navpoints = len(props.nav_points)
        return props.stat_navpoints, False

    props.nav_points.clear()
    for i, obj in enumerate(nav_objs):
        np = props.nav_points.add()
        np.position = tuple(obj.location)
        np.point_type = int(obj.get("point_type", 0))
        np.angle = float(obj.rotation_euler.z)
        obj["point_index"] = i
        obj["point_type"] = np.point_type
        obj["point_angle"] = np.angle

    props.stat_navpoints = len(props.nav_points)
    return props.stat_navpoints, True


def _refresh_navpoints_objects(props):
    """Rebuild nav point empties from props.nav_points to keep indices stable."""
    col = bpy.data.collections.get(YNV_COLLECTION)
    if col is None:
        return

    for obj in list(col.objects):
        if obj.get("ynv_type") in {"nav_point", "navpoints_root"}:
            bpy.data.objects.remove(obj, do_unlink=True)

    _build_navpoints_objs(props, col)


def _sanitize_portals_for_poly_count(props, poly_count):
    """Keep only portals that reference existing polygon indices.

    Returns number of removed portals.
    """
    if poly_count < 0:
        poly_count = 0

    keep = []
    for p in props.portals:
        pf = int(p.poly_from)
        pt = int(p.poly_to)
        if 0 <= pf < poly_count and 0 <= pt < poly_count:
            keep.append({
                "portal_type": int(p.portal_type),
                "angle": float(p.angle),
                "poly_from": pf,
                "poly_to": pt,
                "pos_from": tuple(p.pos_from),
                "pos_to": tuple(p.pos_to),
            })

    removed = len(props.portals) - len(keep)
    if removed <= 0:
        return 0

    props.portals.clear()
    for entry in keep:
        p = props.portals.add()
        p.portal_type = entry["portal_type"]
        p.angle = entry["angle"]
        p.poly_from = entry["poly_from"]
        p.poly_to = entry["poly_to"]
        p.pos_from = entry["pos_from"]
        p.pos_to = entry["pos_to"]

    props.portal_index = min(props.portal_index, len(props.portals) - 1)
    props.stat_portals = len(props.portals)
    return removed


def _edge_lines_valid_for_poly(edge_list, poly, vert_count):
    """Check if cached edge lines are structurally valid for this polygon."""
    if not isinstance(edge_list, list):
        return False
    if len(edge_list) != poly.loop_total:
        return False

    for line in edge_list:
        if not isinstance(line, str) or ":" not in line or "," not in line:
            return False
        try:
            left, right = line.split(",", 1)
            _, a = left.strip().split(":", 1)
            _, b = right.strip().split(":", 1)
            ia = int(a.strip())
            ib = int(b.strip())
        except Exception:
            return False
        if ia < 0 or ib < 0 or ia >= vert_count or ib >= vert_count:
            return False

    return True


def _edge_flag_lines_valid_for_poly(edge_flags_list, expected_count):
    """Check cached EdgesFlags block validity for one polygon."""
    if not isinstance(edge_flags_list, list):
        return False
    if len(edge_flags_list) != expected_count:
        return False

    for line in edge_flags_list:
        if not isinstance(line, str) or ":" not in line or "," not in line:
            return False
        try:
            left, right = line.split(",", 1)
            a0, a1 = left.strip().split(":", 1)
            b0, b1 = right.strip().split(":", 1)
            int(a0.strip()); int(a1.strip()); int(b0.strip()); int(b1.strip())
        except Exception:
            return False
    return True


def _poly_portal_links_valid(portal_links, portal_count):
    """Check per-poly portal link list values are within portal index bounds."""
    if not isinstance(portal_links, list):
        return False
    for x in portal_links:
        try:
            v = int(x)
        except Exception:
            return False
        if v < 0 or v >= portal_count:
            return False
    return True


def _normalize_poly_portal_links(poly_portal_links, poly_count):
    """Align per-face portal link cache length with polygon count."""
    if not isinstance(poly_portal_links, list):
        poly_portal_links = []

    # Force each face entry to be a list.
    normalized = []
    for entry in poly_portal_links:
        normalized.append(entry if isinstance(entry, list) else [])

    if len(normalized) < poly_count:
        normalized.extend([[] for _ in range(poly_count - len(normalized))])
    elif len(normalized) > poly_count:
        normalized = normalized[:poly_count]

    return normalized


# ─────────────────────────────────────────────────────────────────────────────
#  EXPORT XML
# ─────────────────────────────────────────────────────────────────────────────

def _build_ynv_xml(context, props):
    # Prefer scene nav_point empties when present so manual delete/move is reflected in export.
    _sync_navpoints_from_objects(context, props, keep_props_if_no_objects=True)

    root = ET.Element("NavMesh")
    cf = ET.SubElement(root, "ContentFlags"); cf.text = props.content_flags
    sub_val(root, "AreaID", props.area_id)
    for tag, v in [("BBMin", props.bb_min), ("BBMax", props.bb_max)]:
        el = ET.SubElement(root, tag)
        el.set("x", str(int(v[0]))); el.set("y", str(int(v[1]))); el.set("z", f"{v[2]:.7g}")
    bb_size = ET.SubElement(root, "BBSize")
    bb_size.set("x", f"{props.bb_max[0]-props.bb_min[0]:.7g}")
    bb_size.set("y", f"{props.bb_max[1]-props.bb_min[1]:.7g}")
    bb_size.set("z", f"{props.bb_max[2]-props.bb_min[2]:.7g}")

    polys_el   = ET.SubElement(root, "Polygons")
    poly_obj   = next((o for o in context.scene.objects if o.get("ynv_type") == "poly_mesh"), None)
    poly_count = 0
    if poly_obj and poly_obj.type == "MESH":
        mesh = poly_obj.data
        poly_count = len(mesh.polygons)
        removed_portals = _sanitize_portals_for_poly_count(props, poly_count)
        if removed_portals:
            print(f"[YNV] Removed {removed_portals} invalid portal(s) during export (poly index out of range)")

        try:
            b456_data = json.loads(poly_obj.get("ynv_bytes456", "[]"))
        except Exception:
            b456_data = []
        if not isinstance(b456_data, list):
            b456_data = []

        if not b456_data:
            try:
                b45_data = json.loads(poly_obj.get("ynv_bytes45", "[]"))
            except Exception:
                b45_data = []
            if isinstance(b45_data, list):
                b456_data = []
                for pair in b45_data:
                    if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                        b456_data.append([int(pair[0]), int(pair[1]), 0])
                    else:
                        b456_data.append([0, 0, 0])

        try:
            edge_lines = json.loads(poly_obj.get("ynv_edge_lines", "[]"))
        except Exception:
            edge_lines = []
        if not isinstance(edge_lines, list):
            edge_lines = []

        try:
            edge_flag_lines = json.loads(poly_obj.get("ynv_edge_flag_lines", "[]"))
        except Exception:
            edge_flag_lines = []
        if not isinstance(edge_flag_lines, list):
            edge_flag_lines = []

        try:
            poly_portal_links = json.loads(poly_obj.get("ynv_poly_portals", "[]"))
        except Exception:
            poly_portal_links = []

        poly_portal_links = _normalize_poly_portal_links(poly_portal_links, poly_count)

        # If polygon topology has changed (face delete/add), stale edge cache can become invalid.
        # Fallback to regenerated per-face edges in that case.
        if len(edge_lines) != poly_count:
            edge_lines = []
        if len(edge_flag_lines) != poly_count:
            edge_flag_lines = []

        # Keep bytes4/5/6 array aligned with face count.
        if len(b456_data) < poly_count:
            b456_data.extend([[0, 0, 0] for _ in range(poly_count - len(b456_data))])
        elif len(b456_data) > poly_count:
            b456_data = b456_data[:poly_count]

        for i, poly in enumerate(mesh.polygons):
            mi  = poly.material_index
            mat = mesh.materials[mi] if mi < len(mesh.materials) else None
            if mat and "ynv_b0" in mat:
                b0, b1, b2, b3 = mat["ynv_b0"], mat["ynv_b1"], mat["ynv_b2"], mat["ynv_b3"]
            else:
                b0, b1, b2, b3 = 0, 0, 0, 0
            if i < len(b456_data):
                triplet = b456_data[i]
                if isinstance(triplet, (list, tuple)) and len(triplet) >= 3:
                    b4, b5, b6 = int(triplet[0]), int(triplet[1]), int(triplet[2])
                elif isinstance(triplet, (list, tuple)) and len(triplet) >= 2:
                    b4, b5, b6 = int(triplet[0]), int(triplet[1]), 0
                else:
                    b4, b5, b6 = 0, 0, 0
            else:
                b4, b5, b6 = 0, 0, 0

            item     = ET.SubElement(polys_el, "Item")
            flags_el = ET.SubElement(item, "Flags")
            flags_el.text = f"{b0} {b1} {b2} {b3} {b4} {b5} {b6}"

            verts_el  = ET.SubElement(item, "Vertices")
            vert_lines = []
            for vi in poly.vertices:
                v = mesh.vertices[vi].co
                vert_lines.append(f"    {v.x:.7g}, {v.y:.7g}, {v.z:.7g}")
            verts_el.text = "\n" + "\n".join(vert_lines) + "\n   "

            edges_el  = ET.SubElement(item, "Edges")
            if i < len(edge_lines) and _edge_lines_valid_for_poly(edge_lines[i], poly, len(mesh.vertices)):
                final_edges = edge_lines[i]
            else:
                final_edges = ["16383:16383, 16383:16383" for _ in range(poly.loop_total)]
            edges_el.text = "\n" + "\n".join([f"    {ln}" for ln in final_edges]) + "\n   "

            edges_flags_el = ET.SubElement(item, "EdgesFlags")
            if i < len(edge_flag_lines) and _edge_flag_lines_valid_for_poly(edge_flag_lines[i], len(final_edges)):
                final_edge_flags = edge_flag_lines[i]
            else:
                final_edge_flags = ["0:0, 0:0" for _ in range(len(final_edges))]
            edges_flags_el.text = "\n" + "\n".join([f"    {ln}" for ln in final_edge_flags]) + "\n   "

            if i < len(poly_portal_links):
                links = []
                for raw in poly_portal_links[i]:
                    try:
                        idx = int(raw)
                    except Exception:
                        continue
                    if 0 <= idx < len(props.portals):
                        links.append(str(idx))
                if links:
                    p_el = ET.SubElement(item, "Portals")
                    p_el.text = "\n" + "\n".join([f"    {v}" for v in links]) + "\n   "

    portals_el = ET.SubElement(root, "Portals")
    for portal in props.portals:
        item = ET.SubElement(portals_el, "Item")
        sub_val(item, "Type", portal.portal_type)
        sub_val(item, "Angle",    f"{portal.angle:.7g}")
        sub_val(item, "PolyFrom", portal.poly_from)
        sub_val(item, "PolyTo",   portal.poly_to)
        for tag, pos in [("PositionFrom", portal.pos_from), ("PositionTo", portal.pos_to)]:
            el = ET.SubElement(item, tag)
            el.set("x", f"{pos[0]:.7g}"); el.set("y", f"{pos[1]:.7g}"); el.set("z", f"{pos[2]:.7g}")

    points_el = ET.SubElement(root, "Points")
    for np_item in props.nav_points:
        item = ET.SubElement(points_el, "Item")
        sub_val(item, "Type",  np_item.point_type)
        sub_val(item, "Angle", f"{np_item.angle:.7g}")
        pos_el = ET.SubElement(item, "Position")
        pos_el.set("x", f"{np_item.position[0]:.7g}")
        pos_el.set("y", f"{np_item.position[1]:.7g}")
        pos_el.set("z", f"{np_item.position[2]:.7g}")

    return to_xml_string(root)


# ─────────────────────────────────────────────────────────────────────────────
# READ SELECTED POLYGON FLAGS
# ─────────────────────────────────────────────────────────────────────────────

def _read_selected_face_flags(context, props):
    """
    Reads flags from the first selected polygon in Edit Mode
    and copies them to props.selected_poly_flags + fills bytes 4-5.
    Returns (ok, message).
    """
    obj = context.active_object
    if obj is None or obj.type != "MESH" or obj.get("ynv_type") != "poly_mesh":
        return False, "Activate the YNV PolyMesh in Edit Mode."
    if obj.mode != "EDIT":
        return False, "Switch to Edit Mode and select a face."

    mesh = obj.data
    bm   = bmesh.from_edit_mesh(mesh)
    selected_faces = [f for f in bm.faces if f.select]
    if not selected_faces:
        return False, "No face selected."

    face = selected_faces[0]
    fi   = face.index
    mi   = face.material_index

    mat  = mesh.materials[mi] if mi < len(mesh.materials) else None

    # Retrieve b0-b3 from the material
    if mat and "ynv_b0" in mat:
        b0 = int(mat["ynv_b0"]); b1 = int(mat["ynv_b1"])
        b2 = int(mat["ynv_b2"]); b3 = int(mat["ynv_b3"])
    else:
        b0, b1, b2, b3 = 0, 0, 0, 0

    # Retrieve b4-b5 from the object's JSON custom prop
    try:
        b45_data = json.loads(obj.get("ynv_bytes45", "[]"))
        b4, b5   = b45_data[fi] if fi < len(b45_data) else (0, 0)
    except Exception:
        b4, b5 = 0, 0

    # Apply to PropertyGroup flags
    pf = props.selected_poly_flags
    pf.poly_index = fi
    flags_str = f"{b0} {b1} {b2} {b3} {b4} {b5}"
    pf.from_flags_str(flags_str)

    mat_name = mat.name if mat else "(none)"
    labels   = " + ".join(_flag_label_parts(b0, b1, b2, b3))
    return True, f"Face {fi} : [{b0} {b1} {b2} {b3}] {labels} | b4={b4} b5={b5}"


# ─────────────────────────────────────────────────────────────────────────────
# OPERATORS
# ─────────────────────────────────────────────────────────────────────────────

class YNV_OT_Import(Operator):
    """Import a navmesh YNV XML file into Blender"""
    bl_idname  = "gta5_ynv.import_xml"; bl_label = "Import YNV XML"
    bl_options = {"REGISTER", "UNDO"}
    filepath:   StringProperty(subtype="FILE_PATH")
    filter_glob:StringProperty(default="*.xml;*.ynv.xml", options={"HIDDEN"})
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self); return {"RUNNING_MODAL"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        ok, msg, polygons_data = _parse_ynv_xml(self.filepath, props)
        if not ok: self.report({"ERROR"}, msg); return {"CANCELLED"}
        props.filepath = self.filepath
        col = _get_or_create_col(YNV_COLLECTION)
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

        base_name = os.path.basename(self.filepath)
        lower_name = base_name.lower()
        if lower_name.endswith(".ynv.xml"):
            root_name = base_name[:-8]
        else:
            root_name = os.path.splitext(base_name)[0]
        root_obj = _build_ynv_root(root_name, col)

        if polygons_data:
            poly_obj = _build_navmesh_obj(polygons_data, props.area_id)
            _link_obj(poly_obj, col)
            poly_obj.parent = root_obj

        portals_root = _build_portals_objs(props, col)
        portals_root.parent = root_obj
        points_root = _build_navpoints_objs(props, col)
        points_root.parent = root_obj

        n_mats = len(set(m.name for m in bpy.data.materials if m.name.startswith("YNV_")))
        self.report({"INFO"},
            f"YNV imported: {props.stat_polygons} polygons, "
            f"{n_mats} unique materials, "
            f"{props.stat_portals} portals, "
            f"{props.stat_navpoints} points")
        return {"FINISHED"}


class YNV_OT_Export(Operator):
    """Export navmesh to YNV XML"""
    bl_idname  = "gta5_ynv.export_xml"; bl_label = "Export YNV XML"
    bl_options = {"REGISTER"}
    filepath:   StringProperty(subtype="FILE_PATH")
    filter_glob:StringProperty(default="*.xml", options={"HIDDEN"})
    def invoke(self, context, event):
        props = context.scene.gta5_pathing.ynv
        self.filepath = props.filepath or "navmesh.ynv.xml"
        context.window_manager.fileselect_add(self); return {"RUNNING_MODAL"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        poly_obj = next((o for o in context.scene.objects if o.get("ynv_type") == "poly_mesh" and o.type == "MESH"), None)
        poly_count = len(poly_obj.data.polygons) if poly_obj is not None else 0
        removed_portals = _sanitize_portals_for_poly_count(props, poly_count)
        if removed_portals:
            self.report({"WARNING"}, f"{removed_portals} invalid portal(s) removed before export")
        xml_str = _build_ynv_xml(context, props)
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                f.write(xml_str)
        except OSError as e:
            self.report({"ERROR"}, str(e)); return {"CANCELLED"}
        props.filepath = self.filepath
        self.report({"INFO"}, f"YNV exported → {self.filepath}")
        return {"FINISHED"}


class YNV_OT_ReadSelectedFlags(Operator):
    """Reads flags from selected polygon (Edit Mode) and displays in panel"""
    bl_idname  = "gta5_ynv.read_selected_flags"; bl_label = "Read flags from selection"
    bl_options = {"REGISTER"}
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.get("ynv_type") == "poly_mesh" and obj.mode == "EDIT"
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        ok, msg = _read_selected_face_flags(context, props)
        self.report({"INFO" if ok else "WARNING"}, msg)
        return {"FINISHED" if ok else "CANCELLED"}


class YNV_OT_ApplyFlagsPreset(Operator):
    """Applies flag preset to selected faces"""
    bl_idname  = "gta5_ynv.apply_flags_preset"; bl_label = "Apply Preset"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.get("ynv_type") == "poly_mesh" and obj.mode == "EDIT"
    def execute(self, context):
        props  = context.scene.gta5_pathing.ynv
        preset = props.flag_preset
        b0, b1, b2, b3 = FLAG_PRESETS.get(preset, (0,0,0,0))
        return _apply_flags_to_selection(context, props, b0, b1, b2, b3, preset)


class YNV_OT_ApplyCustomFlags(Operator):
    """Applies custom flags from panel to selected faces"""
    bl_idname  = "gta5_ynv.apply_custom_flags"; bl_label = "Apply Custom Flags"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.get("ynv_type") == "poly_mesh" and obj.mode == "EDIT"
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        pf    = props.selected_poly_flags
        flags_str = pf.to_flags_str()
        b0, b1, b2, b3, _b4, _b5, _b6 = _parse_flags_str(flags_str)
        return _apply_flags_to_selection(context, props, b0, b1, b2, b3, "custom")


def _apply_flags_to_selection(context, props, b0, b1, b2, b3, label):
    """Applies a material (b0,b1,b2,b3) to selected faces."""
    obj  = context.active_object
    mesh = obj.data
    mat  = _get_or_create_material(b0, b1, b2, b3)

    # Add the material to the mesh if not already present
    if mat.name not in [m.name for m in mesh.materials]:
        mesh.materials.append(mat)

    mi = list(mesh.materials).index(mat)

    bm = bmesh.from_edit_mesh(mesh)
    count = 0
    b45_raw = obj.get("ynv_bytes45", "[]")
    try:
        b45_data = json.loads(b45_raw)
    except Exception:
        b45_data = []

    try:
        b456_data = json.loads(obj.get("ynv_bytes456", "[]"))
    except Exception:
        b456_data = []

    # Ensure b45_data has enough entries
    while len(b45_data) < len(mesh.polygons):
        b45_data.append([0, 0])
    while len(b456_data) < len(mesh.polygons):
        b456_data.append([0, 0, 0])

    for face in bm.faces:
        if face.select:
            face.material_index = mi
            count += 1

    bmesh.update_edit_mesh(mesh)
    obj["ynv_bytes45"] = json.dumps(b45_data)
    obj["ynv_bytes456"] = json.dumps(b456_data)
    return {"FINISHED"}


class YNV_OT_AddPolygon(Operator):
    """Adds a navmesh quad at cursor with active preset"""
    bl_idname  = "gta5_ynv.add_polygon"; bl_label = "Add Polygon"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props  = context.scene.gta5_pathing.ynv
        col    = _get_or_create_col(YNV_COLLECTION)
        poly_obj = next((o for o in context.scene.objects if o.get("ynv_type") == "poly_mesh"), None)
        if poly_obj is None:
            mesh     = bpy.data.meshes.new("YNV_PolyMesh")
            poly_obj = bpy.data.objects.new(f"YNV_{props.area_id}_PolyMesh", mesh)
            poly_obj["ynv_type"] = "poly_mesh"
            poly_obj["ynv_area_id"] = props.area_id
            poly_obj["ynv_bytes45"] = "[]"
            poly_obj["ynv_bytes456"] = "[]"
            _link_obj(poly_obj, col)

        preset       = props.flag_preset
        b0, b1, b2, b3 = FLAG_PRESETS.get(preset, (0,0,0,0))
        mat          = _get_or_create_material(b0, b1, b2, b3)

        cursor = context.scene.cursor.location
        s      = 2.5
        z      = cursor.z

        bm = bmesh.new()
        bm.from_mesh(poly_obj.data)
        verts = [
            bm.verts.new((cursor.x - s, cursor.y - s, z)),
            bm.verts.new((cursor.x + s, cursor.y - s, z)),
            bm.verts.new((cursor.x + s, cursor.y + s, z)),
            bm.verts.new((cursor.x - s, cursor.y + s, z)),
        ]
        bm.faces.new(verts)
        bm.to_mesh(poly_obj.data)
        bm.free()
        poly_obj.data.update()

        # Assign material to last face
        mesh = poly_obj.data
        if mat.name not in [m.name for m in mesh.materials]:
            mesh.materials.append(mat)
        mi = list(mesh.materials).index(mat)
        mesh.polygons[-1].material_index = mi

        # Update b45_data
        try:
            b45_data = json.loads(poly_obj.get("ynv_bytes45","[]"))
        except Exception:
            b45_data = []
        b45_data.append([0, 0])
        poly_obj["ynv_bytes45"] = json.dumps(b45_data)

        try:
            b456_data = json.loads(poly_obj.get("ynv_bytes456", "[]"))
        except Exception:
            b456_data = []
        b456_data.append([0, 0, 0])
        poly_obj["ynv_bytes456"] = json.dumps(b456_data)

        try:
            poly_portals = json.loads(poly_obj.get("ynv_poly_portals", "[]"))
        except Exception:
            poly_portals = []
        if not isinstance(poly_portals, list):
            poly_portals = []
        poly_portals.append([])
        poly_obj["ynv_poly_portals"] = json.dumps(poly_portals)

        props.stat_polygons = len(mesh.polygons)
        labels = " + ".join(_flag_label_parts(b0, b1, b2, b3))
        self.report({"INFO"}, f"Polygon added: [{b0} {b1} {b2} {b3}] {labels}")
        return {"FINISHED"}


class YNV_OT_AddPortal(Operator):
    """Adds a NavMesh portal"""
    bl_idname  = "gta5_ynv.add_portal"; bl_label = "Add Portal"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        p = props.portals.add(); p.portal_type = 1
        c = context.scene.cursor.location
        p.pos_from = (c.x, c.y, c.z); p.pos_to = (c.x + 1, c.y, c.z + 5)
        props.portal_index = len(props.portals) - 1
        props.stat_portals = len(props.portals)
        return {"FINISHED"}


class YNV_OT_RemovePortal(Operator):
    """Removes selected portal"""
    bl_idname  = "gta5_ynv.remove_portal"; bl_label = "Remove Portal"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        props = context.scene.gta5_pathing.ynv
        return 0 <= props.portal_index < len(props.portals)
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        props.portals.remove(props.portal_index)
        props.portal_index = min(props.portal_index, len(props.portals) - 1)
        props.stat_portals = len(props.portals)
        return {"FINISHED"}


class YNV_OT_AddNavPoint(Operator):
    """Adds a nav point at cursor"""
    bl_idname  = "gta5_ynv.add_nav_point"; bl_label = "Add Nav Point"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props  = context.scene.gta5_pathing.ynv
        np     = props.nav_points.add()
        cursor = context.scene.cursor.location
        np.position = (cursor.x, cursor.y, cursor.z)
        props.nav_point_index = len(props.nav_points) - 1
        props.stat_navpoints  = len(props.nav_points)
        _refresh_navpoints_objects(props)
        return {"FINISHED"}


class YNV_OT_RemoveNavPoint(Operator):
    """Removes selected nav point"""
    bl_idname  = "gta5_ynv.remove_nav_point"; bl_label = "Remove Nav Point"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        props = context.scene.gta5_pathing.ynv
        return 0 <= props.nav_point_index < len(props.nav_points)
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        props.nav_points.remove(props.nav_point_index)
        props.nav_point_index = min(props.nav_point_index, len(props.nav_points) - 1)
        props.stat_navpoints  = len(props.nav_points)
        _refresh_navpoints_objects(props)
        return {"FINISHED"}


class YNV_OT_SyncFromObjects(Operator):
    """Syncs portals and nav points from empties"""
    bl_idname  = "gta5_ynv.sync_from_objects"; bl_label = "Sync from Objects"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        count, _ = _sync_navpoints_from_objects(context, props, keep_props_if_no_objects=False)
        self.report({"INFO"}, f"Sync: {count} nav points")
        return {"FINISHED"}


class YNV_OT_ComputeBBox(Operator):
    """Recalculates bounding box from mesh"""
    bl_idname  = "gta5_ynv.compute_bbox"; bl_label = "Compute BB"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props    = context.scene.gta5_pathing.ynv
        poly_obj = next((o for o in context.scene.objects if o.get("ynv_type") == "poly_mesh"), None)
        if poly_obj is None or poly_obj.type != "MESH":
            self.report({"WARNING"}, "No YNV mesh"); return {"CANCELLED"}
        verts = [poly_obj.matrix_world @ v.co for v in poly_obj.data.vertices]
        if not verts: return {"CANCELLED"}
        props.bb_min = (min(v.x for v in verts), min(v.y for v in verts), min(v.z for v in verts))
        props.bb_max = (max(v.x for v in verts), max(v.y for v in verts), max(v.z for v in verts))
        self.report({"INFO"}, "Bounding Box calculated.")
        return {"FINISHED"}


class YNV_OT_SplitMesh(Operator):
    """Splits mesh according to Tile Size / Offset grid"""
    bl_idname  = "gta5_ynv.split_mesh"; bl_label = "Split Mesh"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        self.report({"INFO"}, "Split Mesh: use an external tool (CodeWalker) for tile splitting.")
        return {"FINISHED"}


_classes = [
    YNV_OT_Import, YNV_OT_Export,
    YNV_OT_ReadSelectedFlags, YNV_OT_ApplyFlagsPreset, YNV_OT_ApplyCustomFlags,
    YNV_OT_AddPolygon,
    YNV_OT_AddPortal,    YNV_OT_RemovePortal,
    YNV_OT_AddNavPoint,  YNV_OT_RemoveNavPoint,
    YNV_OT_SyncFromObjects, YNV_OT_ComputeBBox, YNV_OT_SplitMesh,
]

def register():
    for cls in _classes:
        try: bpy.utils.unregister_class(cls)
        except Exception: pass
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_classes):
        try: bpy.utils.unregister_class(cls)
        except Exception: pass
