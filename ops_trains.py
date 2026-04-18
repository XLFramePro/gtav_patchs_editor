"""
ops_trains.py — Train Tracks (.dat) v4.1

CHANGES:
  ✅ All 4 GTA5 train flags (0=Normal, 1=Boost, 4=Switch, 5=Boost+Switch)
  ✅ Each track point is an EMPTY in Blender (selectable, movable individually)
  ✅ Parent empty hierarchy per imported file
  ✅ Direct point selection updates panel
  ✅ Curve generation still available as option
  ✅ Precise .6g float format
"""
import bpy, os, math
from bpy.types import Operator
from bpy.props import StringProperty, IntProperty, FloatProperty, BoolProperty

_COL_PREFIX = "GTA5PE_TRAINS_"

TRAIN_FLAG_ITEMS = [
    ("0", "Normal",         "Standard track point",       0),
    ("1", "Boost",          "Accelerated section",        1),
    ("4", "Switch/Junction","Track switch/junction point", 4),
    ("5", "Boost+Switch",   "Accelerated junction",       5),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _flag_color(flag):
    """Colour for EMPTY display by flag type."""
    return {0:"PLAIN_AXES", 1:"ARROWS", 4:"CIRCLE", 5:"SPHERE"}.get(flag, "PLAIN_AXES")

def _flag_size(flag):
    return 0.8 if flag == 4 else (0.6 if flag == 5 else 0.4)

def _get_or_create_col(name):
    col = bpy.data.collections.get(name)
    if not col:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col

def _link(obj, col):
    for c in obj.users_collection: c.objects.unlink(obj)
    col.objects.link(obj)

# ── Parse ─────────────────────────────────────────────────────────────────────

def _parse(filepath, props):
    props.points.clear()
    try:
        with open(filepath, "r") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
    except Exception as e:
        return False, str(e)

    if not lines: return False, "Empty file"
    try:
        count = int(lines[0])
    except ValueError:
        count = len(lines) - 1

    for line in lines[1:count+1]:
        parts = line.split()
        if len(parts) < 3: continue
        pt = props.points.add()
        pt.position = (float(parts[0]), float(parts[1]), float(parts[2]))
        pt.flag = int(parts[3]) if len(parts) >= 4 else 0

    return True, "OK"

# ── Build point empties ───────────────────────────────────────────────────────

def _make_point_empty(pt, i, col, parent):
    obj = bpy.data.objects.new(f"TRAIN_{i:04d}_F{pt.flag}", None)
    obj.empty_display_type = _flag_color(pt.flag)
    obj.empty_display_size = _flag_size(pt.flag)
    obj.location = tuple(pt.position)
    obj["trains_type"] = "point"
    obj["point_idx"]   = i
    obj["flag"]        = pt.flag
    if parent: obj.parent = parent
    _link(obj, col)
    return obj

def _build_objects(props, col, root_empty):
    for i, pt in enumerate(props.points):
        _make_point_empty(pt, i, col, root_empty)

# ── Export ────────────────────────────────────────────────────────────────────

def _export(props):
    # Sync positions from Blender objects
    col_name = props.get("col_name", "")
    col = bpy.data.collections.get(col_name) if col_name else None
    if col:
        for obj in col.objects:
            if obj.get("trains_type") == "point":
                idx = obj.get("point_idx", -1)
                if 0 <= idx < len(props.points):
                    pt = props.points[idx]
                    pt.position = tuple(obj.location)
                    pt.flag     = obj.get("flag", 0)

    count = len(props.points)
    lines = [str(count)]
    for pt in props.points:
        x, y, z = pt.position
        lines.append(f"{x:.6g} {y:.6g} {z:.6g} {pt.flag}")
    return "\n".join(lines) + "\n"

# ── Sync from objects ──────────────────────────────────────────────────────────

def _sync_from_objects(props):
    col_name = props.get("col_name", "")
    col = bpy.data.collections.get(col_name) if col_name else None
    if not col: return 0
    count = 0
    for obj in sorted(col.objects, key=lambda o: o.get("point_idx", 9999)):
        if obj.get("trains_type") == "point":
            idx = obj.get("point_idx", -1)
            if 0 <= idx < len(props.points):
                pt = props.points[idx]
                pt.position = tuple(obj.location)
                pt.flag     = obj.get("flag", 0)
                count += 1
    return count

# ── OPERATORS ─────────────────────────────────────────────────────────────────

class TRAINS_OT_Import(Operator):
    """Import a GTA5 train tracks .dat file"""
    bl_idname = "gta5pe.trains_import"; bl_label = "Import .dat"
    bl_options = {"REGISTER", "UNDO"}
    filepath:    StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.dat", options={"HIDDEN"})

    def invoke(self, ctx, e):
        ctx.window_manager.fileselect_add(self); return {"RUNNING_MODAL"}

    def execute(self, ctx):
        props    = ctx.scene.gta5pe.trains
        filename = os.path.basename(self.filepath)
        col_name = _COL_PREFIX + os.path.splitext(filename)[0]

        ok, msg = _parse(self.filepath, props)
        if not ok: self.report({"ERROR"}, msg); return {"CANCELLED"}

        props.filepath    = self.filepath
        props["col_name"] = col_name

        old = bpy.data.collections.get(col_name)
        if old:
            for o in list(old.objects): bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(old)

        col = _get_or_create_col(col_name)
        root = bpy.data.objects.new(filename, None)
        root.empty_display_type = "PLAIN_AXES"; root.empty_display_size = 0.01
        root["trains_type"] = "root"; _link(root, col)
        _build_objects(props, col, root)

        switches = sum(1 for pt in props.points if pt.flag == 4)
        boosts   = sum(1 for pt in props.points if pt.flag in (1, 5))
        self.report({"INFO"},
            f"Trains: {len(props.points)} points  {switches} switches  {boosts} boosts")
        return {"FINISHED"}


class TRAINS_OT_New(Operator):
    """Create an empty train track"""
    bl_idname = "gta5pe.trains_new"; bl_label = "New Train Track"
    bl_options = {"REGISTER", "UNDO"}
    filename: StringProperty(name="Name", default="new_trains")

    def invoke(self, ctx, e): return ctx.window_manager.invoke_props_dialog(self)

    def execute(self, ctx):
        props = ctx.scene.gta5pe.trains
        props.points.clear(); props.filepath = ""
        col_name = _COL_PREFIX + self.filename
        props["col_name"] = col_name
        old = bpy.data.collections.get(col_name)
        if old:
            for o in list(old.objects): bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(old)
        col = _get_or_create_col(col_name)
        root = bpy.data.objects.new(self.filename + ".dat", None)
        root.empty_display_type = "PLAIN_AXES"; root.empty_display_size = 0.01
        root["trains_type"] = "root"; _link(root, col)
        self.report({"INFO"}, f"New train track: {self.filename}")
        return {"FINISHED"}


class TRAINS_OT_Export(Operator):
    """Export train tracks to .dat"""
    bl_idname = "gta5pe.trains_export"; bl_label = "Export .dat"
    bl_options = {"REGISTER"}
    filepath:    StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.dat", options={"HIDDEN"})

    def invoke(self, ctx, e):
        self.filepath = ctx.scene.gta5pe.trains.filepath or "trains.dat"
        ctx.window_manager.fileselect_add(self); return {"RUNNING_MODAL"}

    def execute(self, ctx):
        props = ctx.scene.gta5pe.trains
        data  = _export(props)
        try:
            with open(self.filepath, "w") as f: f.write(data)
        except OSError as e:
            self.report({"ERROR"}, str(e)); return {"CANCELLED"}
        props.filepath = self.filepath
        self.report({"INFO"}, f"Exported {len(props.points)} points → {self.filepath}")
        return {"FINISHED"}


class TRAINS_OT_AddPoint(Operator):
    """Add a train track point at the 3D cursor"""
    bl_idname = "gta5pe.trains_add_normal"; bl_label = "Add Normal Point"
    bl_options = {"REGISTER", "UNDO"}
    flag: IntProperty(name="Flag", default=0)

    def execute(self, ctx):
        props = ctx.scene.gta5pe.trains
        pt = props.points.add()
        pt.position = tuple(ctx.scene.cursor.location)
        pt.flag = self.flag
        props.point_idx = len(props.points) - 1

        col_name = props.get("col_name", "")
        col = bpy.data.collections.get(col_name)
        if not col: col = _get_or_create_col(_COL_PREFIX + "default"); props["col_name"] = _COL_PREFIX + "default"
        parent = next((o for o in col.objects if o.get("trains_type") == "root"), None)
        _make_point_empty(pt, props.point_idx, col, parent)
        return {"FINISHED"}


class TRAINS_OT_AddJunction(Operator):
    """Add a switch/junction point at the 3D cursor"""
    bl_idname = "gta5pe.trains_add_junction"; bl_label = "Add Switch Point"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, ctx):
        bpy.ops.gta5pe.trains_add_normal(flag=4)
        return {"FINISHED"}


class TRAINS_OT_RemovePoint(Operator):
    """Delete the active track point"""
    bl_idname = "gta5pe.trains_remove_point"; bl_label = "Delete Point"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, ctx): p = ctx.scene.gta5pe.trains; return 0 <= p.point_idx < len(p.points)

    def execute(self, ctx):
        props = ctx.scene.gta5pe.trains; idx = props.point_idx
        col_name = props.get("col_name", "")
        col = bpy.data.collections.get(col_name)

        if col:
            for obj in list(col.objects):
                if obj.get("trains_type") == "point" and obj.get("point_idx") == idx:
                    bpy.data.objects.remove(obj, do_unlink=True); break
            # Shift indices
            for obj in col.objects:
                if obj.get("trains_type") == "point":
                    cur = obj.get("point_idx", -1)
                    if cur > idx:
                        obj["point_idx"] = cur - 1
                        obj.name = f"TRAIN_{cur-1:04d}_F{obj.get('flag',0)}"

        props.points.remove(idx)
        props.point_idx = max(0, min(idx, len(props.points) - 1))
        return {"FINISHED"}


class TRAINS_OT_SetFlag(Operator):
    """Set flag on the active track point"""
    bl_idname = "gta5pe.trains_set_flag"; bl_label = "Set Point Flag"
    bl_options = {"REGISTER", "UNDO"}
    flag: IntProperty(name="Flag", default=0)

    @classmethod
    def poll(cls, ctx): p = ctx.scene.gta5pe.trains; return 0 <= p.point_idx < len(p.points)

    def execute(self, ctx):
        props = ctx.scene.gta5pe.trains; idx = props.point_idx
        props.points[idx].flag = self.flag
        col_name = props.get("col_name", "")
        col = bpy.data.collections.get(col_name)
        if col:
            for obj in col.objects:
                if obj.get("trains_type") == "point" and obj.get("point_idx") == idx:
                    obj["flag"] = self.flag
                    obj.empty_display_type = _flag_color(self.flag)
                    obj.empty_display_size = _flag_size(self.flag)
                    obj.name = f"TRAIN_{idx:04d}_F{self.flag}"
                    break
        return {"FINISHED"}


class TRAINS_OT_ToggleJunction(Operator):
    """Toggle between Normal (0) and Switch/Junction (4) for active point"""
    bl_idname = "gta5pe.trains_toggle_junction"; bl_label = "Toggle Switch"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, ctx): p = ctx.scene.gta5pe.trains; return 0 <= p.point_idx < len(p.points)

    def execute(self, ctx):
        props = ctx.scene.gta5pe.trains; pt = props.points[props.point_idx]
        new_flag = 4 if pt.flag == 0 else 0
        bpy.ops.gta5pe.trains_set_flag(flag=new_flag)
        return {"FINISHED"}


class TRAINS_OT_Sync(Operator):
    """Sync positions and flags from Blender point empties → props"""
    bl_idname = "gta5pe.trains_sync_curve"; bl_label = "Sync from Objects"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, ctx):
        props = ctx.scene.gta5pe.trains
        count = _sync_from_objects(props)
        self.report({"INFO"}, f"Synced {count} points")
        return {"FINISHED"}


class TRAINS_OT_GenFromCurve(Operator):
    """Generate track points from the active Bezier/NURBS/POLY curve"""
    bl_idname = "gta5pe.trains_gen_from_curve"; bl_label = "Generate from Active Curve"
    bl_options = {"REGISTER", "UNDO"}
    flag: IntProperty(name="Point Flag", default=0)

    @classmethod
    def poll(cls, ctx):
        return ctx.active_object and ctx.active_object.type == "CURVE"

    def execute(self, ctx):
        props  = ctx.scene.gta5pe.trains
        curve  = ctx.active_object
        points = []

        for spline in curve.data.splines:
            if spline.type == "POLY":
                for p in spline.points:
                    wco = curve.matrix_world @ p.co.to_3d()
                    points.append(tuple(wco))
            elif spline.type in ("BEZIER", "NURBS"):
                # Sample along the spline
                steps = max(2, len(spline.bezier_points) * 4 if spline.type == "BEZIER" else len(spline.points) * 4)
                for s in range(steps):
                    t = s / (steps - 1)
                    # Use spline.calc_length and interpolation
                    wco = curve.matrix_world @ spline.calc_length()
                    # Fallback: use bezier points directly
                from mathutils.geometry import interpolate_bezier
                if spline.type == "BEZIER":
                    bpts = spline.bezier_points
                    for i in range(len(bpts) - 1):
                        for j in range(8):
                            t = j / 8.0
                            p0 = curve.matrix_world @ bpts[i].co
                            h1 = curve.matrix_world @ bpts[i].handle_right
                            h2 = curve.matrix_world @ bpts[i+1].handle_left
                            p1 = curve.matrix_world @ bpts[i+1].co
                            pts_seg = interpolate_bezier(p0, h1, h2, p1, 1)
                            points.append(tuple(pts_seg[0]))
                    points.append(tuple(curve.matrix_world @ bpts[-1].co))

        if not points:
            self.report({"WARNING"}, "No points extracted from curve")
            return {"CANCELLED"}

        props.points.clear()
        col_name = props.get("col_name", _COL_PREFIX + "curve")
        props["col_name"] = col_name
        old = bpy.data.collections.get(col_name)
        if old:
            for o in list(old.objects): bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(old)
        col = _get_or_create_col(col_name)
        root = bpy.data.objects.new("curve.dat", None)
        root.empty_display_type = "PLAIN_AXES"; root.empty_display_size = 0.01
        root["trains_type"] = "root"; _link(root, col)

        for pos in points:
            pt = props.points.add()
            pt.position = pos
            pt.flag     = self.flag
        for i, pt in enumerate(props.points):
            _make_point_empty(pt, i, col, root)

        self.report({"INFO"}, f"Generated {len(props.points)} points from curve")
        return {"FINISHED"}


class TRAINS_OT_TrackActive(Operator):
    """Modal: follow active object to update point_idx in panel."""
    bl_idname = "gta5pe.trains_track_active"; bl_label = "Track Active Train Point"
    bl_options = set()
    _last = None

    def modal(self, ctx, event):
        if not hasattr(ctx.scene, "gta5pe"): return {"CANCELLED"}
        if ctx.scene.gta5pe.tab != "TRAINS":  return {"PASS_THROUGH"}
        if event.type not in ("LEFTMOUSE", "MOUSEMOVE", "TIMER"): return {"PASS_THROUGH"}
        obj = ctx.active_object
        if obj is self.__class__._last: return {"PASS_THROUGH"}
        self.__class__._last = obj
        if obj and obj.get("trains_type") == "point":
            idx   = obj.get("point_idx", -1)
            props = ctx.scene.gta5pe.trains
            if 0 <= idx < len(props.points) and props.point_idx != idx:
                props.point_idx = idx
                for a in ctx.screen.areas: a.tag_redraw()
        return {"PASS_THROUGH"}

    def invoke(self, ctx, e):
        ctx.window_manager.modal_handler_add(self); return {"RUNNING_MODAL"}


_CLASSES = [
    TRAINS_OT_Import, TRAINS_OT_New, TRAINS_OT_Export,
    TRAINS_OT_AddPoint, TRAINS_OT_AddJunction, TRAINS_OT_RemovePoint,
    TRAINS_OT_SetFlag, TRAINS_OT_ToggleJunction,
    TRAINS_OT_Sync, TRAINS_OT_GenFromCurve, TRAINS_OT_TrackActive,
]

def register():
    for cls in _CLASSES:
        try: bpy.utils.unregister_class(cls)
        except Exception: pass
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_CLASSES):
        try: bpy.utils.unregister_class(cls)
        except Exception: pass
