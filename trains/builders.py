import bpy

from .constants import TRACK_COLOR


def _get_or_create_collection(name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def _link_obj(obj, col):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    col.objects.link(obj)


def _get_track_material():
    name = "TRAINS_Track"
    mat = bpy.data.materials.get(name)
    if mat:
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
    bsdf.inputs["Base Color"].default_value = TRACK_COLOR
    bsdf.inputs["Metallic"].default_value = 0.8
    bsdf.inputs["Roughness"].default_value = 0.3
    return mat


def _build_train_curve(props, col):
    curve_data = bpy.data.curves.new("TRAINS_TrackCurve", type="CURVE")
    curve_data.dimensions = "3D"
    curve_data.resolution_u = 4
    curve_data.bevel_depth = 0.1
    curve_data.bevel_resolution = 0

    spline = curve_data.splines.new("POLY")
    n = len(props.points)
    spline.points.add(n - 1)

    for i, pt in enumerate(props.points):
        spline.points[i].co = (*pt.position, 1.0)
        spline.points[i].radius = float(pt.flag)

    obj = bpy.data.objects.new("TRAINS_TrackCurve", curve_data)
    obj["trains_type"] = "track_curve"
    obj["track_name"] = props.track_name
    obj["point_count"] = n
    obj["junction_count"] = props.stat_junctions
    curve_data.materials.append(_get_track_material())
    _link_obj(obj, col)
    return obj


def _build_junction_markers(props, col, track_obj):
    root = bpy.data.objects.new("TRAINS_Junctions", None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.1
    root["trains_type"] = "junctions_root"
    _link_obj(root, col)

    for i, pt in enumerate(props.points):
        if pt.flag == 4:
            obj = bpy.data.objects.new(f"TRAINS_Junction_{i}", None)
            obj.empty_display_type = "ARROWS"
            obj.empty_display_size = 3.0
            obj.location = pt.position
            obj["trains_type"] = "junction"
            obj["point_index"] = i
            obj["junction_flag"] = pt.flag
            obj.parent = root
            _link_obj(obj, col)

    return root
