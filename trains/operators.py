"""Trains operators layer.

Parsing/serialization and object builders are split into dedicated modules.
"""

import bpy
from bpy.types import Operator
from bpy.props import StringProperty, IntProperty
from mathutils import Vector

from .constants import TRAINS_COLLECTION, TRACK_COLOR, JUNCTION_COLOR
from .builders import _get_or_create_collection, _link_obj, _build_train_curve, _build_junction_markers
from .io import _parse_trains_dat, _build_trains_dat


# ─────────────────────────────────────────────────────────────────────────────
#  OPERATORS
# ─────────────────────────────────────────────────────────────────────────────

class TRAINS_OT_New(Operator):
    """Create a new empty train track workspace in Blender"""
    bl_idname  = "gta5_trains.new_track"
    bl_label   = "New Track"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.gta5_pathing.trains
        props.filepath = ""
        props.points.clear()

        cursor = context.scene.cursor.location
        pt = props.points.add()
        pt.position = (cursor.x, cursor.y, cursor.z)
        pt.flag = 0

        props.point_index = 0
        props.stat_points = 1
        props.stat_junctions = 0

        col = _get_or_create_collection(TRAINS_COLLECTION)
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

        track_obj = _build_train_curve(props, col)
        _build_junction_markers(props, col, track_obj)

        self.report({"INFO"}, "New train track created")
        return {"FINISHED"}

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
        self.report({"WARNING"}, "Import is disabled in Creator mode. Use 'New Track'.")
        return {"CANCELLED"}


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
    TRAINS_OT_New,
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
