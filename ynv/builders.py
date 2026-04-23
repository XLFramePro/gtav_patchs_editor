import bmesh
import bpy
import json
import math
import os

from mathutils import Vector

from .constants import YNV_COLLECTION
from .io import _parse_flags_str


def _flag_label_parts(b0, b1, b2, b3):
    """Returns a list of strings describing active flags."""
    parts = []
    if b0 & 128:
        parts.append("Water")
    if b0 & 64:
        parts.append("TooSteep")
    if b0 & 8:
        parts.append("Underground")
    if b0 & 4:
        parts.append("Pavement")
    if b0 & 2:
        parts.append("LargePoly")
    if b0 & 1:
        parts.append("SmallPoly")
    if b1 & 64:
        parts.append("Isolated")
    if b1 & 32:
        parts.append("Interior")
    if b1 & 16:
        parts.append("NearCar")
    audio = b1 & 7
    if audio:
        parts.append(f"Aud{audio}")
    if b2 & 8:
        parts.append("TrainTrack")
    if b2 & 16:
        parts.append("Shallow")
    if b2 & 4:
        parts.append("AlongEdge")
    if b2 & 2:
        parts.append("Road")
    if b2 & 1:
        parts.append("Spawn")
    ped = (b2 >> 5) & 7
    if ped:
        parts.append(f"Ped{ped}")
    if b3:
        parts.append(f"Cov{b3:02X}")
    return parts if parts else ["Default"]


def _flag_color(b0, b1, b2, b3):
    """Returns RGBA (0-1) according to surface priority."""
    if b0 & 128:
        return (0.05, 0.15, 0.85, 0.85)
    if b0 & 8:
        return (0.15, 0.45, 0.15, 0.85)
    if b1 & 32:
        return (0.85, 0.45, 0.10, 0.85)
    if b1 & 64:
        return (0.85, 0.10, 0.10, 0.80)
    if b2 & 8:
        return (0.55, 0.35, 0.05, 0.85)
    if b2 & 16:
        return (0.15, 0.70, 0.90, 0.80)
    if (b0 & 4) and b3:
        return (0.60, 0.82, 0.30, 0.85)
    if (b2 & 2) and b3:
        return (0.92, 0.72, 0.08, 0.85)
    if b0 & 4:
        return (0.42, 0.78, 0.42, 0.85)
    if b2 & 2:
        return (0.78, 0.78, 0.18, 0.85)
    if b3:
        return (0.78, 0.10, 0.78, 0.80)
    if b2 & 1:
        return (0.18, 0.78, 0.85, 0.80)
    return (0.50, 0.50, 0.50, 0.75)


def _mat_key(b0, b1, b2, b3):
    return f"YNV_{b0:03d}_{b1:03d}_{b2:03d}_{b3:03d}"


def _mat_name(b0, b1, b2, b3):
    label = "_".join(_flag_label_parts(b0, b1, b2, b3))
    base = f"YNV_{label}"
    return base[:63]


def _get_or_create_material(b0, b1, b2, b3):
    key = _mat_key(b0, b1, b2, b3)
    name = _mat_name(b0, b1, b2, b3)

    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = next((m for m in bpy.data.materials if m.name.startswith(key)), None)

    if mat is not None:
        return mat

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    color = _flag_color(b0, b1, b2, b3)
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.85
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (*color[:3], 1.0)
        bsdf.inputs["Emission Strength"].default_value = 0.05

    mat.use_backface_culling = False
    if hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"

    mat.diffuse_color = color

    mat["ynv_b0"] = b0
    mat["ynv_b1"] = b1
    mat["ynv_b2"] = b2
    mat["ynv_b3"] = b3

    return mat


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
    return os.path.join(os.path.dirname(__file__), "assets", filename)


def _load_marker_mesh_from_glb(cache_name):
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
    mesh = _load_marker_mesh_from_glb(cache_name)
    if mesh is not None:
        return mesh, True
    return _get_or_create_cube_mesh(fallback_name, size=fallback_size), False


def _apply_sollumz_type(obj, type_name):
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
    return f"{i + 1:02d}"


def _build_ynv_root(name, col):
    root = bpy.data.objects.new(name, None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 1.0
    root["ynv_type"] = "root"
    _link_obj(root, col)
    _apply_sollumz_type(root, "NAVMESH")
    return root


def _compose_navmesh_root_name(props):
    return f"{props.navmesh_name_prefix}[{props.navmesh_name_x}][{props.navmesh_name_y}]"


def _find_ynv_root(context):
    return next((o for o in context.scene.objects if o.get("ynv_type") == "root"), None)


def _build_navmesh_obj(polygons_data, area_id):
    vert_map = {}
    verts_list = []
    faces_list = []
    face_flags = []
    face_edges = []
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

    mat_index_map = {}
    for i, (b0, b1, b2, b3, b4, b5, b6) in enumerate(face_flags):
        key = _mat_key(b0, b1, b2, b3)
        if key not in mat_index_map:
            mat = _get_or_create_material(b0, b1, b2, b3)
            mesh.materials.append(mat)
            mat_index_map[key] = len(mesh.materials) - 1

    for i, (b0, b1, b2, b3, b4, b5, b6) in enumerate(face_flags):
        key = _mat_key(b0, b1, b2, b3)
        mesh.polygons[i].material_index = mat_index_map[key]

    obj = bpy.data.objects.new("NavMesh Poly Mesh", mesh)
    obj["ynv_type"] = "poly_mesh"
    obj["ynv_area_id"] = area_id
    _apply_sollumz_type(obj, "NAVMESH_POLY_MESH")
    b456_data = [(ff[4], ff[5], ff[6]) for ff in face_flags]
    obj["ynv_bytes456"] = json.dumps(b456_data)
    obj["ynv_bytes45"] = json.dumps([(ff[4], ff[5]) for ff in face_flags])
    obj["ynv_edge_lines"] = json.dumps(face_edges)
    obj["ynv_edge_flag_lines"] = json.dumps(face_edge_flags)
    obj["ynv_poly_portals"] = json.dumps(face_portals)
    return obj


def _build_portals_objs(props, col):
    root = bpy.data.objects.new("Portals", None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.5
    root["ynv_type"] = "portals_root"
    _link_obj(root, col)

    portal_mesh, portal_has_arrow = _get_or_create_marker_mesh("YNV_CubeArrowPortalMesh", "YNV_PortalCube", 0.35)
    point_mesh, point_has_arrow = _get_or_create_marker_mesh("YNV_CubeArrowPointMesh", "YNV_PortalPointCube", 0.22)

    for i, portal in enumerate(props.portals):
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
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.1
    root["ynv_type"] = "navpoints_root"
    _link_obj(root, col)
    nav_mesh, nav_has_arrow = _get_or_create_marker_mesh("YNV_CubeArrowNavPointMesh", "YNV_NavPointCube", 0.28)

    for i, np_item in enumerate(props.nav_points):
        obj = bpy.data.objects.new(f"NavMesh Point.{_idx_name(i)}", nav_mesh)
        obj.location = np_item.position
        obj.rotation_euler = (0, 0, np_item.angle)
        obj["ynv_type"] = "nav_point"
        obj["point_index"] = i
        obj["point_type"] = np_item.point_type
        obj["point_angle"] = np_item.angle
        obj.parent = root
        _link_obj(obj, col)
        _apply_sollumz_type(obj, "NAVMESH_POINT")
        if not nav_has_arrow:
            _add_direction_arrow(obj, col, 0.0, size=0.85)
    return root


def _iter_navpoint_objects(context):
    nav_objs = [o for o in context.scene.objects if o.get("ynv_type") == "nav_point"]
    return sorted(nav_objs, key=lambda o: (int(o.get("point_index", 10 ** 9)), o.name))


def _sync_navpoints_from_objects(context, props, keep_props_if_no_objects=False):
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
    col = bpy.data.collections.get(YNV_COLLECTION)
    if col is None:
        return

    for obj in list(col.objects):
        if obj.get("ynv_type") in {"nav_point", "navpoints_root"}:
            bpy.data.objects.remove(obj, do_unlink=True)

    _build_navpoints_objs(props, col)


def _read_selected_face_flags(context, props):
    obj = context.active_object
    if obj is None or obj.type != "MESH" or obj.get("ynv_type") != "poly_mesh":
        return False, "Activate the YNV PolyMesh in Edit Mode."
    if obj.mode != "EDIT":
        return False, "Switch to Edit Mode and select a face."

    mesh = obj.data
    bm = bmesh.from_edit_mesh(mesh)
    selected_faces = [f for f in bm.faces if f.select]
    if not selected_faces:
        return False, "No face selected."

    face = selected_faces[0]
    fi = face.index
    mi = face.material_index

    mat = mesh.materials[mi] if mi < len(mesh.materials) else None

    if mat and "ynv_b0" in mat:
        b0 = int(mat["ynv_b0"])
        b1 = int(mat["ynv_b1"])
        b2 = int(mat["ynv_b2"])
        b3 = int(mat["ynv_b3"])
    else:
        b0, b1, b2, b3 = 0, 0, 0, 0

    try:
        b456_data = json.loads(obj.get("ynv_bytes456", "[]"))
        if fi < len(b456_data) and isinstance(b456_data[fi], (list, tuple)):
            trip = list(b456_data[fi])
            while len(trip) < 3:
                trip.append(0)
            b4, b5, b6 = int(trip[0]), int(trip[1]), int(trip[2])
        else:
            b4, b5, b6 = 0, 0, 0
    except Exception:
        b4, b5, b6 = 0, 0, 0

    props.part_id_current = b6

    pf = props.selected_poly_flags
    pf.poly_index = fi
    flags_str = f"{b0} {b1} {b2} {b3} {b4} {b5}"
    pf.from_flags_str(flags_str)

    labels = " + ".join(_flag_label_parts(b0, b1, b2, b3))
    return True, f"Face {fi} : [{b0} {b1} {b2} {b3}] {labels} | b4={b4} b5={b5} part={b6}"


def _ensure_b456_for_mesh(obj):
    mesh = obj.data
    try:
        b456_data = json.loads(obj.get("ynv_bytes456", "[]"))
    except Exception:
        b456_data = []
    if not isinstance(b456_data, list):
        b456_data = []

    while len(b456_data) < len(mesh.polygons):
        b456_data.append([0, 0, 0])
    if len(b456_data) > len(mesh.polygons):
        b456_data = b456_data[: len(mesh.polygons)]
    for i, trip in enumerate(b456_data):
        if not isinstance(trip, (list, tuple)):
            b456_data[i] = [0, 0, 0]
            continue
        t = list(trip)
        while len(t) < 3:
            t.append(0)
        b456_data[i] = [int(t[0]), int(t[1]), int(t[2])]
    return b456_data


def _get_active_poly_mesh(context):
    obj = context.active_object
    if obj is not None and obj.type == "MESH" and obj.get("ynv_type") == "poly_mesh":
        return obj
    return next((o for o in context.scene.objects if o.get("ynv_type") == "poly_mesh" and o.type == "MESH"), None)


def _apply_flags_to_selection(context, props, b0, b1, b2, b3, label):
    obj = context.active_object
    mesh = obj.data
    mat = _get_or_create_material(b0, b1, b2, b3)

    if mat.name not in [m.name for m in mesh.materials]:
        mesh.materials.append(mat)

    mi = list(mesh.materials).index(mat)

    bm = bmesh.from_edit_mesh(mesh)
    b45_raw = obj.get("ynv_bytes45", "[]")
    try:
        b45_data = json.loads(b45_raw)
    except Exception:
        b45_data = []

    try:
        b456_data = json.loads(obj.get("ynv_bytes456", "[]"))
    except Exception:
        b456_data = []

    while len(b45_data) < len(mesh.polygons):
        b45_data.append([0, 0])
    while len(b456_data) < len(mesh.polygons):
        b456_data.append([0, 0, 0])

    for face in bm.faces:
        if face.select:
            face.material_index = mi

    bmesh.update_edit_mesh(mesh)
    obj["ynv_bytes45"] = json.dumps(b45_data)
    obj["ynv_bytes456"] = json.dumps(b456_data)
    return {"FINISHED"}
