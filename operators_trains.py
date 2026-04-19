"""
operators_trains.py — Import/Export/Edit operators for train tracks (trains*.dat).

Format trains*.dat :
  Line 1: number of points (int)
  Following lines: X Y Z FLAG
    FLAG = 0  : normal track point
    FLAG = 4  : switch / junction (train can diverge)
    FLAG = 1/5: rare variants (sometimes used for special segments)

The track is a continuous 3D curve. Switches allow creating
complex train networks with diverging paths.
"""

import bpy
import os
import math
from bpy.types import Operator
from bpy.props import StringProperty, IntProperty, BoolProperty, EnumProperty
from mathutils import Vector


# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

TRAINS_COLLECTION = "TRAINS_TrackEditor"
TRACK_COLOR       = (0.2, 0.2, 0.2, 1.0)   # dark grey = rail
JUNCTION_COLOR    = (1.0, 0.4, 0.0, 1.0)   # orange = switch


# ─────────────────────────────────────────────────────────────────────────────
#  PARSE .DAT
# ─────────────────────────────────────────────────────────────────────────────

def _parse_trains_dat(filepath, props):
    """Parses trains*.dat and fills the point collection."""
    props.points.clear()

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
    except OSError as e:
        return False, f"Read error: {e}"

    if not lines:
        return False, "Empty file."

    # First line = expected number of points
    try:
        expected = int(lines[0])
    except ValueError:
        return False, f"Invalid line 1 (expected integer): '{lines[0]}'"

    data_lines = lines[1:]
    count = 0
    junctions = 0

    for line in data_lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            x    = float(parts[0])
            y    = float(parts[1])
            z    = float(parts[2])
            flag = int(parts[3]) if len(parts) >= 4 else 0
        except ValueError:
            continue

        pt = props.points.add()
        pt.position = (x, y, z)
        pt.flag     = flag
        count      += 1
        if flag == 4:
            junctions += 1

    props.stat_points    = count
    props.stat_junctions = junctions
    props.track_name     = os.path.splitext(os.path.basename(filepath))[0]
    return True, "OK"


# ─────────────────────────────────────────────────────────────────────────────
#  EXPORT .DAT
# ─────────────────────────────────────────────────────────────────────────────

def _build_trains_dat(context, props) -> str:
    """Rebuilds the .dat file from Blender data."""
    # Sync from Blender curve if it exists
    curve_obj = next((o for o in context.scene.objects
                      if o.get("trains_type") == "track_curve"), None)

    if curve_obj and curve_obj.type == "CURVE":
        # Extract curve points
        props.points.clear()
        curve = curve_obj.data
        for spline in curve.splines:
            if spline.type == "POLY":
                for pt in spline.points:
                    item = props.points.add()
                    item.position = (
                        curve_obj.matrix_world @ Vector(pt.co[:3])
                    )
                    item.flag = int(pt.radius) if pt.radius in (0, 1, 4, 5) else 0
            elif spline.type == "BEZIER":
                for pt in spline.bezier_points:
                    item = props.points.add()
                    item.position = tuple(curve_obj.matrix_world @ pt.co)
                    item.flag = 0

    # Write the DAT
    n = len(props.points)
    lines = [str(n)]
    for pt in props.points:
        x, y, z = pt.position
        lines.append(f"{x:.3f} {y:.3f} {z:.3f} {pt.flag}")
    return "\r\n".join(lines) + "\r\n"


# ─────────────────────────────────────────────────────────────────────────────
#  BLENDER OBJECTS
# ─────────────────────────────────────────────────────────────────────────────

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
    out  = nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = TRACK_COLOR
    bsdf.inputs["Metallic"].default_value   = 0.8
    bsdf.inputs["Roughness"].default_value  = 0.3
    return mat


def _build_train_curve(props, col):
    """Creates a Blender Curve object representing the train track."""
    curve_data = bpy.data.curves.new("TRAINS_TrackCurve", type="CURVE")
    curve_data.dimensions    = "3D"
    curve_data.resolution_u  = 4
    curve_data.bevel_depth   = 0.1
    curve_data.bevel_resolution = 0

    # Create a poly spline with all track points
    spline = curve_data.splines.new("POLY")
    n = len(props.points)
    spline.points.add(n - 1)

    for i, pt in enumerate(props.points):
        spline.points[i].co = (*pt.position, 1.0)
        # Store flag in radius for later retrieval
        spline.points[i].radius = float(pt.flag)

    obj = bpy.data.objects.new("TRAINS_TrackCurve", curve_data)
    obj["trains_type"]    = "track_curve"
    obj["track_name"]     = props.track_name
    obj["point_count"]    = n
    obj["junction_count"] = props.stat_junctions
    mat = _get_track_material()
    curve_data.materials.append(mat)
    _link_obj(obj, col)
    return obj


def _build_junction_markers(props, col, track_obj):
    """Creates orange empties on junctions."""
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
            obj["trains_type"]   = "junction"
            obj["point_index"]   = i
            obj["junction_flag"] = pt.flag
            obj.parent = root
            _link_obj(obj, col)

    return root


# ─────────────────────────────────────────────────────────────────────────────
#  OPERATORS
# ─────────────────────────────────────────────────────────────────────────────

class TRAINS_OT_Import(Operator):
    """Import a trains*.dat file into Blender"""
    bl_idname  = "gta5_trains.import_dat"
    bl_label   = "Import trains.dat"
    bl_options = {"REGISTER", "UNDO"}

    filepath:   StringProperty(subtype="FILE_PATH")
    filter_glob:StringProperty(default="*.dat", options={"HIDDEN"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        props = context.scene.gta5_pathing.trains
        ok, msg = _parse_trains_dat(self.filepath, props)
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}
        props.filepath = self.filepath

        col = _get_or_create_collection(TRAINS_COLLECTION)
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

        track_obj = _build_train_curve(props, col)
        _build_junction_markers(props, col, track_obj)

        self.report({"INFO"},
                    f"Train imported: {props.stat_points} points, "
                    f"{props.stat_junctions} junctions — '{props.track_name}'")
        return {"FINISHED"}


class TRAINS_OT_Export(Operator):
    """Exports the train track to a .dat file"""
    bl_idname  = "gta5_trains.export_dat"
    bl_label   = "Export trains.dat"
    bl_options = {"REGISTER"}

    filepath:   StringProperty(subtype="FILE_PATH")
    filter_glob:StringProperty(default="*.dat", options={"HIDDEN"})

    def invoke(self, context, event):
        props = context.scene.gta5_pathing.trains
        self.filepath = props.filepath or f"{props.track_name}.dat"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        props = context.scene.gta5_pathing.trains
        dat_str = _build_trains_dat(context, props)
        try:
            with open(self.filepath, "w", encoding="utf-8", newline="") as f:
                f.write(dat_str)
        except OSError as e:
            self.report({"ERROR"}, f"Write error: {e}")
            return {"CANCELLED"}
        props.filepath = self.filepath
        self.report({"INFO"}, f"Trains exported ({len(props.points)} pts) → {self.filepath}")
        return {"FINISHED"}


class TRAINS_OT_AddPoint(Operator):
    """Adds a track point at the 3D cursor"""
    bl_idname  = "gta5_trains.add_point"
    bl_label   = "Add Point"
    bl_options = {"REGISTER", "UNDO"}

    flag: IntProperty(name="Flag", default=0, min=0, max=5)

    def execute(self, context):
        props = context.scene.gta5_pathing.trains
        cursor = context.scene.cursor.location
        pt = props.points.add()
        pt.position = (cursor.x, cursor.y, cursor.z)
        pt.flag     = self.flag
        props.point_index    = len(props.points) - 1
        props.stat_points    = len(props.points)
        props.stat_junctions = sum(1 for p in props.points if p.flag == 4)

        # Add the point to the existing curve
        curve_obj = next((o for o in context.scene.objects
                          if o.get("trains_type") == "track_curve"), None)
        if curve_obj and curve_obj.type == "CURVE":
            spline = curve_obj.data.splines[0]
            spline.points.add(1)
            spline.points[-1].co = (*pt.position, 1.0)
            spline.points[-1].radius = float(pt.flag)
        return {"FINISHED"}


class TRAINS_OT_RemovePoint(Operator):
    """Removes the selected track point"""
    bl_idname  = "gta5_trains.remove_point"
    bl_label   = "Remove Point"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        props = context.scene.gta5_pathing.trains
        return 0 <= props.point_index < len(props.points)

    def execute(self, context):
        props = context.scene.gta5_pathing.trains
        props.points.remove(props.point_index)
        props.point_index    = min(props.point_index, len(props.points) - 1)
        props.stat_points    = len(props.points)
        props.stat_junctions = sum(1 for p in props.points if p.flag == 4)
        return {"FINISHED"}


class TRAINS_OT_MarkJunction(Operator):
    """Marks the selected point as a junction (flag=4)"""
    bl_idname  = "gta5_trains.mark_junction"
    bl_label   = "Mark Junction"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        props = context.scene.gta5_pathing.trains
        return 0 <= props.point_index < len(props.points)

    def execute(self, context):
        props = context.scene.gta5_pathing.trains
        pt = props.points[props.point_index]
        pt.flag = 0 if pt.flag == 4 else 4
        props.stat_junctions = sum(1 for p in props.points if p.flag == 4)
        self.report({"INFO"}, f"Point {props.point_index}: flag={'4 (junction)' if pt.flag==4 else '0 (normal)'}")
        return {"FINISHED"}


class TRAINS_OT_SyncFromCurve(Operator):
    """Syncs points from the Blender curve"""
    bl_idname  = "gta5_trains.sync_from_curve"
    bl_label   = "Sync from Curve"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.gta5_pathing.trains
        curve_obj = next((o for o in context.scene.objects
                          if o.get("trains_type") == "track_curve"), None)
        if curve_obj is None or curve_obj.type != "CURVE":
            self.report({"WARNING"}, "No train curve found.")
            return {"CANCELLED"}

        props.points.clear()
        count = 0
        for spline in curve_obj.data.splines:
            if spline.type == "POLY":
                for p in spline.points:
                    wco = curve_obj.matrix_world @ Vector(p.co[:3])
                    pt = props.points.add()
                    pt.position = tuple(wco)
                    flag = int(p.radius) if p.radius in (0, 1, 4, 5) else 0
                    pt.flag = flag
                    count += 1

        props.stat_points    = count
        props.stat_junctions = sum(1 for p in props.points if p.flag == 4)
        self.report({"INFO"}, f"Synced: {count} points extracted from curve")
        return {"FINISHED"}


class TRAINS_OT_GenerateFromCurve(Operator):
    """Generate a train track from the selected Curve object"""
    bl_idname  = "gta5_trains.generate_from_curve"
    bl_label   = "Generate from Selected Curve"
    bl_options = {"REGISTER", "UNDO"}

    resolution: IntProperty(
        name="Resolution",
        description="Number of points per Blender unit",
        default=2, min=1, max=20,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "CURVE"

    def execute(self, context):
        obj = context.active_object
        props = context.scene.gta5_pathing.trains
        props.points.clear()

        # Evaluate the curve to get a mesh
        depsgraph = context.evaluated_depsgraph_get()
        eval_obj  = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()

        for v in mesh.vertices:
            wco = obj.matrix_world @ v.co
            pt = props.points.add()
            pt.position = tuple(wco)
            pt.flag = 0

        eval_obj.to_mesh_clear()

        props.stat_points    = len(props.points)
        props.stat_junctions = 0

        # Tag the object as track_curve
        obj["trains_type"] = "track_curve"
        obj["track_name"]  = obj.name

        self.report({"INFO"}, f"Track generated: {props.stat_points} points")
        return {"FINISHED"}


_classes = [
    TRAINS_OT_Import,
    TRAINS_OT_Export,
    TRAINS_OT_AddPoint,
    TRAINS_OT_RemovePoint,
    TRAINS_OT_MarkJunction,
    TRAINS_OT_SyncFromCurve,
    TRAINS_OT_GenerateFromCurve,
]


def register():
    for cls in _classes:
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
