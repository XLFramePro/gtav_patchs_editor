"""YMT operators layer.

Parsing/serialization and object builders are split into dedicated modules.
"""

import bpy
import os
from bpy.types import Operator
from bpy.props import StringProperty, IntProperty

from .constants import YMT_COLLECTION, ITYPE_NAMES, SCENARIO_COLORS
from .builders import _get_or_create_col, _link_obj, _build_ymt_objects
from .io import _parse_ymt_xml, _build_ymt_xml


# ── OPERATORS ──────────────────────────────────────────────────────────────────

class YMT_OT_New(Operator):
    """Create a new empty YMT workspace in Blender"""
    bl_idname = "gta5_ymt.new_file"; bl_label = "New YMT"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.gta5_pathing.ymt
        props.filepath = ""
        props.scenario_points.clear()
        props.chaining_nodes.clear()
        props.chaining_edges.clear()
        props.chains.clear()
        props.entity_overrides.clear()
        props.point_index = -1
        props.chain_node_index = -1
        props.chain_edge_index = -1
        props.chain_index = -1
        props.entity_override_index = -1
        props.stat_points = 0
        props.stat_nodes = 0
        props.stat_edges = 0
        props.stat_chains = 0

        col = _get_or_create_col(YMT_COLLECTION)
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        _build_ymt_objects(props, col, ITYPE_NAMES)

        self.report({"INFO"}, "New empty YMT created")
        return {"FINISHED"}

class YMT_OT_Import(Operator):
    """Import a Scenario YMT XML file"""
    bl_idname = "gta5_ymt.import_xml"; bl_label = "Import YMT XML"
    bl_options = {"REGISTER", "UNDO"}
    filepath:   StringProperty(subtype="FILE_PATH")
    filter_glob:StringProperty(default="*.xml;*.ymt;*.ymt.xml", options={"HIDDEN"})
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self); return {"RUNNING_MODAL"}
    def execute(self, context):
        self.report({"WARNING"}, "Import is disabled in Creator mode. Use 'New YMT'.")
        return {"CANCELLED"}


class YMT_OT_Export(Operator):
    """Export scenarios to .ymt XML (OpenIV/CodeWalker compatible)"""
    bl_idname = "gta5_ymt.export_xml"; bl_label = "Export .ymt XML"
    bl_options = {"REGISTER"}
    filepath:   StringProperty(subtype="FILE_PATH")
    filter_glob:StringProperty(default="*.ymt;*.ymt.xml;*.xml", options={"HIDDEN"})
    def invoke(self, context, event):
        props = context.scene.gta5_pathing.ymt
        # Keep the same filename with .ymt.xml extension
        base = props.filepath or "scenario.ymt.xml"
        if not base.endswith(".ymt.xml") and not base.endswith(".ymt"):
            base = os.path.splitext(base)[0] + ".ymt.xml"
        self.filepath = base
        context.window_manager.fileselect_add(self); return {"RUNNING_MODAL"}
    def execute(self, context):
        props   = context.scene.gta5_pathing.ymt
        xml_str = _build_ymt_xml(context, props)
        try:
            with open(self.filepath, "w", encoding="utf-8") as f: f.write(xml_str)
        except OSError as e:
            self.report({"ERROR"}, str(e)); return {"CANCELLED"}
        props.filepath = self.filepath
        self.report({"INFO"}, f"YMT exported → {self.filepath}")
        return {"FINISHED"}


class YMT_OT_AddScenarioPoint(Operator):
    """Adds a scenario point at the cursor"""
    bl_idname = "gta5_ymt.add_scenario_point"; bl_label = "Add Scenario Point"
    bl_options = {"REGISTER", "UNDO"}
    itype: IntProperty(name="iType", default=1, min=0, max=21)
    def execute(self, context):
        props = context.scene.gta5_pathing.ymt
        sp = props.scenario_points.add()
        sp.itype = self.itype; sp.time_start = 0; sp.time_end = 24
        sp.avail_mp_sp = 1; sp.time_till_leaves = 255
        cursor = context.scene.cursor.location
        sp.position = (cursor.x, cursor.y, cursor.z, 0.0)
        props.point_index = len(props.scenario_points) - 1
        props.stat_points = len(props.scenario_points)
        col = _get_or_create_col(YMT_COLLECTION)
        i   = props.point_index
        name= ITYPE_NAMES.get(self.itype, f"type{self.itype}")
        obj = bpy.data.objects.new(f"YMT_SP_{i}_{name}", None)
        obj.empty_display_type = "SINGLE_ARROW"; obj.empty_display_size = 1.0
        obj.location = (sp.position[0], sp.position[1], sp.position[2])
        obj["ymt_type"] = "scenario_point"; obj["sp_index"] = i
        obj["itype"] = sp.itype; obj["flags"] = sp.flags
        obj["time_start"] = sp.time_start; obj["time_end"] = sp.time_end
        _link_obj(obj, col)
        return {"FINISHED"}


class YMT_OT_RemoveScenarioPoint(Operator):
    """Removes the selected scenario point"""
    bl_idname = "gta5_ymt.remove_scenario_point"; bl_label = "Remove Point"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        props = context.scene.gta5_pathing.ymt
        return 0 <= props.point_index < len(props.scenario_points)
    def execute(self, context):
        props = context.scene.gta5_pathing.ymt
        props.scenario_points.remove(props.point_index)
        props.point_index = min(props.point_index, len(props.scenario_points) - 1)
        props.stat_points = len(props.scenario_points)
        return {"FINISHED"}


class YMT_OT_AddChainingNode(Operator):
    """Adds a chaining node at the cursor"""
    bl_idname = "gta5_ymt.add_chaining_node"; bl_label = "Add Chaining Node"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ymt
        cn = props.chaining_nodes.add()
        cursor = context.scene.cursor.location
        cn.position = (cursor.x, cursor.y, cursor.z)
        cn.scenario_type = "standing"; cn.has_outgoing = True
        props.chain_node_index = len(props.chaining_nodes) - 1
        props.stat_nodes = len(props.chaining_nodes)
        col = _get_or_create_col(YMT_COLLECTION)
        i   = props.chain_node_index
        obj = bpy.data.objects.new(f"YMT_CNode_{i}_standing", None)
        obj.empty_display_type = "CIRCLE"; obj.empty_display_size = 0.5
        obj.location = cn.position; obj["ymt_type"] = "chaining_node"; obj["cn_index"] = i
        _link_obj(obj, col)
        return {"FINISHED"}


class YMT_OT_AddChainingEdge(Operator):
    """Adds an edge between two chaining nodes"""
    bl_idname = "gta5_ymt.add_chaining_edge"; bl_label = "Add Edge"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ymt
        ce = props.chaining_edges.add(); ce.node_from = 0; ce.node_to = 0; ce.nav_mode = 1; ce.nav_speed = 2
        props.chain_edge_index = len(props.chaining_edges) - 1
        props.stat_edges = len(props.chaining_edges)
        return {"FINISHED"}


class YMT_OT_RemoveChainingEdge(Operator):
    """Removes the selected chaining edge"""
    bl_idname = "gta5_ymt.remove_chaining_edge"; bl_label = "Remove Edge"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        props = context.scene.gta5_pathing.ymt
        return 0 <= props.chain_edge_index < len(props.chaining_edges)
    def execute(self, context):
        props = context.scene.gta5_pathing.ymt
        props.chaining_edges.remove(props.chain_edge_index)
        props.chain_edge_index = min(props.chain_edge_index, len(props.chaining_edges) - 1)
        props.stat_edges = len(props.chaining_edges)
        return {"FINISHED"}


class YMT_OT_RemoveAllEdgesFromNode(Operator):
    """Removes all edges from the selected node"""
    bl_idname = "gta5_ymt.remove_all_edges_node"; bl_label = "Remove Node Edges"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        props = context.scene.gta5_pathing.ymt
        return 0 <= props.chain_node_index < len(props.chaining_nodes)
    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
    def execute(self, context):
        props = context.scene.gta5_pathing.ymt
        ni    = props.chain_node_index
        to_remove = [i for i, e in enumerate(props.chaining_edges) if e.node_from == ni or e.node_to == ni]
        for i in reversed(to_remove): props.chaining_edges.remove(i)
        props.chain_edge_index = min(props.chain_edge_index, len(props.chaining_edges) - 1)
        props.stat_edges = len(props.chaining_edges)
        self.report({"INFO"}, f"{len(to_remove)} edge(s) removed")
        return {"FINISHED"}


class YMT_OT_SyncFromObjects(Operator):
    """Syncs from Blender empties"""
    bl_idname = "gta5_ymt.sync_from_objects"; bl_label = "Sync from Objects"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ymt
        cnt = 0
        for obj in context.scene.objects:
            if obj.get("ymt_type") == "scenario_point":
                idx = obj.get("sp_index", -1)
                if 0 <= idx < len(props.scenario_points):
                    sp = props.scenario_points[idx]
                    sp.position = (obj.location.x, obj.location.y, obj.location.z, obj.rotation_euler.z)
                    sp.itype = obj.get("itype", sp.itype); cnt += 1
            elif obj.get("ymt_type") == "chaining_node":
                idx = obj.get("cn_index", -1)
                if 0 <= idx < len(props.chaining_nodes):
                    props.chaining_nodes[idx].position = tuple(obj.location); cnt += 1
        self.report({"INFO"}, f"Synced: {cnt} objects updated")
        return {"FINISHED"}


_classes = [
    YMT_OT_New,
    YMT_OT_Import, YMT_OT_Export,
    YMT_OT_AddScenarioPoint, YMT_OT_RemoveScenarioPoint,
    YMT_OT_AddChainingNode,
    YMT_OT_AddChainingEdge, YMT_OT_RemoveChainingEdge, YMT_OT_RemoveAllEdgesFromNode,
    YMT_OT_SyncFromObjects,
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
