"""
operators_ynd.py — Complete PathNodes YND.
"""
import bpy
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty, IntProperty
from mathutils import Vector
from .constants import YND_COLLECTION, YND_CURVE_PRESETS
from .io import (
    _apply_link_flags,
    _apply_node_flags,
    _build_ynd_xml,
    _link_flags_to_ints,
    _node_flags_to_ints,
    _node_is_freeway,
    _node_is_junction,
    _node_is_vehicle,
    _parse_ynd_xml,
    _update_ynd_stats,
)
from .builders import (
    _build_node_index_map,
    _build_ynd_link_objects,
    _build_ynd_objects,
    _calc_area_id_from_position,
    _collect_curve_neighbor_relations,
    _curve_node_key,
    _find_node_by_area_id,
    _find_node_index_for_object,
    _find_ynd_source_curve,
    _flat_curve_point_keys,
    _get_or_create_col,
    _iter_curve_point_chains,
    _link_obj,
    _next_free_node_id,
    _next_preserved_or_free_node_id,
    _populate_ynd_from_curve,
    _preset_link_flags,
    _preset_node_flags,
    _prune_invalid_local_links,
    _recalc_all_link_lengths,
    _refresh_ynd_link_objects,
    _remove_links_targeting_node,
    _repair_duplicate_local_ids,
    _snapshot_curve_node_state,
    _sync_positions_from_node_objects,
    _update_curve_links_only,
)


# ─────────────────────────────────────────────────────────────────────────────
#  OPÉRATEURS
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────

class YND_OT_New(Operator):
    """Create a new empty YND workspace in Blender"""
    bl_idname = "gta5_ynd.new_file"; bl_label = "New YND"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        props.filepath = ""
        props.nodes.clear()
        props.node_index = -1
        _update_ynd_stats(props)

        col = _get_or_create_col(YND_COLLECTION)
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        _build_ynd_objects(props, col)

        self.report({"INFO"}, "New empty YND created")
        return {"FINISHED"}

class YND_OT_Import(Operator):
    """Import a PathNodes YND XML file"""
    bl_idname = "gta5_ynd.import_xml"; bl_label = "Import YND XML"
    bl_options = {"REGISTER", "UNDO"}
    filepath:   StringProperty(subtype="FILE_PATH")
    filter_glob:StringProperty(default="*.xml;*.ynd.xml", options={"HIDDEN"})
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self); return {"RUNNING_MODAL"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        ok, msg = _parse_ynd_xml(self.filepath, props)
        if not ok:
            self.report({"ERROR"}, f"YND import failed: {msg}")
            return {"CANCELLED"}
        col = _get_or_create_col(YND_COLLECTION)
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        _build_ynd_objects(props, col)
        props.filepath = self.filepath
        self.report({"INFO"}, f"YND imported: {len(props.nodes)} nodes from '{self.filepath}'")
        return {"FINISHED"}


class YND_OT_Export(Operator):
    """Export PathNodes to YND XML"""
    bl_idname = "gta5_ynd.export_xml"; bl_label = "Export YND XML"
    bl_options = {"REGISTER"}
    filepath:   StringProperty(subtype="FILE_PATH")
    filter_glob:StringProperty(default="*.xml", options={"HIDDEN"})
    def invoke(self, context, event):
        props = context.scene.gta5_pathing.ynd
        self.filepath = props.filepath or "nodes.ynd.xml"
        context.window_manager.fileselect_add(self); return {"RUNNING_MODAL"}
    def execute(self, context):
        props   = context.scene.gta5_pathing.ynd
        xml_str = _build_ynd_xml(context, props)
        try:
            with open(self.filepath, "w", encoding="utf-8") as f: f.write(xml_str)
        except OSError as e:
            self.report({"ERROR"}, str(e)); return {"CANCELLED"}
        props.filepath = self.filepath
        self.report({"INFO"}, f"YND exported → {self.filepath}")
        return {"FINISHED"}


class YND_OT_AddVehicleNode(Operator):
    """Adds a vehicle node at the 3D cursor"""
    bl_idname = "gta5_ynd.add_vehicle_node"; bl_label = "Add Vehicle Node"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        n = props.nodes.add()
        n.area_id    = props.area_id
        n.node_id    = _next_free_node_id(props.nodes, n.area_id)
        cursor       = context.scene.cursor.location
        n.position   = (cursor.x, cursor.y, cursor.z)
        # Default vehicle flags: Normal speed, GPS enabled
        _apply_node_flags(n, 2, 0, 0, 64, 134, 2)
        props.node_index   = len(props.nodes) - 1
        _update_ynd_stats(props)
        col = _get_or_create_col(YND_COLLECTION)
        obj = bpy.data.objects.new(f"YND_V_{n.area_id}_{n.node_id}", None)
        obj.empty_display_type = "CUBE"; obj.empty_display_size = 0.5
        obj.location = n.position; obj.lock_rotation = (True,True,True); obj.lock_scale = (True,True,True)
        obj["ynd_type"]="node"; obj["node_index"]=props.node_index
        obj["node_area_id"]=n.area_id; obj["node_id"]=n.node_id
        obj["is_vehicle"]=True; obj["is_freeway"]=False; obj["is_junction"]=False
        _link_obj(obj, col)
        self.report({"INFO"}, f"Vehicle node added: {n.area_id}:{n.node_id}")
        return {"FINISHED"}


class YND_OT_AddPedNode(Operator):
    """Adds a pedestrian node at the 3D cursor"""
    bl_idname = "gta5_ynd.add_ped_node"; bl_label = "Add Pedestrian Node"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        n = props.nodes.add()
        n.area_id  = props.area_id
        n.node_id  = _next_free_node_id(props.nodes, n.area_id)
        cursor     = context.scene.cursor.location
        n.position = (cursor.x, cursor.y, cursor.z)
        # flags1 with special_type PED_CROSSING (value 10 << 3 = 80)
        _apply_node_flags(n, 2, 80, 0, 8, 2, 2)
        props.node_index   = len(props.nodes) - 1
        _update_ynd_stats(props)
        col = _get_or_create_col(YND_COLLECTION)
        obj = bpy.data.objects.new(f"YND_P_{n.area_id}_{n.node_id}", None)
        obj.empty_display_type = "SPHERE"; obj.empty_display_size = 0.3
        obj.location = n.position; obj.lock_rotation = (True,True,True); obj.lock_scale = (True,True,True)
        obj["ynd_type"]="node"; obj["node_index"]=props.node_index
        obj["node_area_id"]=n.area_id; obj["node_id"]=n.node_id
        obj["is_vehicle"]=False; obj["is_freeway"]=False; obj["is_junction"]=False
        _link_obj(obj, col)
        self.report({"INFO"}, f"Pedestrian node added: {n.area_id}:{n.node_id}")
        return {"FINISHED"}


class YND_OT_RemoveNode(Operator):
    """Removes active node and all incoming links from other nodes"""
    bl_idname = "gta5_ynd.remove_node"; bl_label = "Remove Node"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        p = context.scene.gta5_pathing.ynd
        return 0 <= p.node_index < len(p.nodes)
    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        idx   = props.node_index
        node  = props.nodes[idx]
        r_area, r_id = node.area_id, node.node_id

        # Remove corresponding node empties to prevent stale sync mappings.
        to_remove = [
            obj for obj in context.scene.objects
            if obj.get("ynd_type") == "node"
            and int(obj.get("node_area_id", -1)) == int(r_area)
            and int(obj.get("node_id", -1)) == int(r_id)
        ]
        for obj in to_remove:
            bpy.data.objects.remove(obj, do_unlink=True)

        # Remove every reference to deleted node from remaining nodes.
        removed_links = _remove_links_targeting_node(props, r_area, r_id)
        props.nodes.remove(idx)
        # Safety pass after removal to catch any stale references.
        removed_links += _remove_links_targeting_node(props, r_area, r_id)
        _prune_invalid_local_links(props)

        # Reindex remaining node empties.
        node_index_map = _build_node_index_map(props.nodes)
        for obj in context.scene.objects:
            if obj.get("ynd_type") != "node":
                continue
            mapped_idx = _find_node_index_for_object(obj, props, node_index_map)
            if mapped_idx >= 0:
                obj["node_index"] = mapped_idx

        props.node_index   = min(idx, len(props.nodes) - 1)
        _update_ynd_stats(props)

        _refresh_ynd_link_objects(props)
        self.report({"INFO"}, f"Node removed: {r_area}:{r_id} ({removed_links} link(s) removed)")
        return {"FINISHED"}


class YND_OT_AddLink(Operator):
    """Adds an outgoing link to the active node"""
    bl_idname = "gta5_ynd.add_link"; bl_label = "Add Link"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        p = context.scene.gta5_pathing.ynd
        return 0 <= p.node_index < len(p.nodes)
    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        node  = props.nodes[props.node_index]
        lk = node.links.add()
        lk.to_area_id  = node.area_id
        lk.to_node_id  = 0
        lk.link_length = 10
        node.link_index = len(node.links) - 1
        _refresh_ynd_link_objects(props)
        return {"FINISHED"}


class YND_OT_RemoveLink(Operator):
    """Removes the active link from the node"""
    bl_idname = "gta5_ynd.remove_link"; bl_label = "Remove Link"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        p = context.scene.gta5_pathing.ynd
        if not (0 <= p.node_index < len(p.nodes)): return False
        return 0 <= p.nodes[p.node_index].link_index < len(p.nodes[p.node_index].links)
    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        node  = props.nodes[props.node_index]
        node.links.remove(node.link_index)
        node.link_index = min(node.link_index, len(node.links) - 1)
        _refresh_ynd_link_objects(props)
        return {"FINISHED"}


class YND_OT_RemoveAllLinks(Operator):
    """Removes ALL links from the active node"""
    bl_idname = "gta5_ynd.remove_all_links"; bl_label = "Remove All Links"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        p = context.scene.gta5_pathing.ynd
        return 0 <= p.node_index < len(p.nodes)
    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        node  = props.nodes[props.node_index]
        count = len(node.links)
        node.links.clear(); node.link_index = -1
        _refresh_ynd_link_objects(props)
        self.report({"INFO"}, f"{count} link(s) removed")
        return {"FINISHED"}


class YND_OT_LinkTwoNodes(Operator):
    """Creates a link from the active node to a target node"""
    bl_idname = "gta5_ynd.link_two_nodes"; bl_label = "Link to Target Node"
    bl_options = {"REGISTER", "UNDO"}
    target_node_id: IntProperty(name="Target Node ID", default=0, min=0)
    target_area_id: IntProperty(name="Target Area ID", default=400, min=0)
    bidirectional:  BoolProperty(name="Bidirectional", default=True)
    @classmethod
    def poll(cls, context):
        p = context.scene.gta5_pathing.ynd
        return 0 <= p.node_index < len(p.nodes)
    def invoke(self, context, event):
        props = context.scene.gta5_pathing.ynd
        self.target_area_id = props.nodes[props.node_index].area_id
        return context.window_manager.invoke_props_dialog(self)
    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        src   = props.nodes[props.node_index]
        target = next((n for n in props.nodes
                       if n.area_id == self.target_area_id and n.node_id == self.target_node_id), None)
        dist   = int(min(255, (Vector(src.position) - Vector(target.position)).length)) if target else 10
        lk = src.links.add()
        lk.to_area_id  = self.target_area_id
        lk.to_node_id  = self.target_node_id
        lk.link_length = dist
        if self.bidirectional and target:
            lk2 = target.links.add()
            lk2.to_area_id  = src.area_id
            lk2.to_node_id  = src.node_id
            lk2.link_length = dist
        _refresh_ynd_link_objects(props)
        self.report({"INFO"}, f"Link {'↔' if self.bidirectional else '→'} created, L={dist}")
        return {"FINISHED"}


class YND_OT_GenerateFromCurve(Operator):
    """Generate YND nodes and links from the active Blender curve"""
    bl_idname = "gta5_ynd.generate_from_curve"; bl_label = "Generate from Active Curve"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "CURVE"

    def execute(self, context):
        curve_obj = context.active_object
        props = context.scene.gta5_pathing.ynd
        ok, msg = _populate_ynd_from_curve(
            curve_obj,
            props,
            props.curve_preset,
            bidirectional=props.curve_bidirectional,
            append_mode=True,
        )
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}

        col = _get_or_create_col(YND_COLLECTION)
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        _build_ynd_objects(props, col)

        curve_obj["ynd_type"] = "source_curve"
        curve_obj["ynd_curve_preset"] = props.curve_preset
        curve_obj["ynd_curve_bidirectional"] = props.curve_bidirectional
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class YND_OT_SyncFromCurve(Operator):
    """Rebuild YND nodes and links from the source Blender curve"""
    bl_idname = "gta5_ynd.sync_from_curve"; bl_label = "Sync from Curve"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _find_ynd_source_curve(context) is not None

    def execute(self, context):
        curve_obj = _find_ynd_source_curve(context)
        if curve_obj is None:
            self.report({"WARNING"}, "No YND source curve found.")
            return {"CANCELLED"}

        props = context.scene.gta5_pathing.ynd
        preset_key = curve_obj.get("ynd_curve_preset", props.curve_preset)
        bidirectional = bool(curve_obj.get("ynd_curve_bidirectional", props.curve_bidirectional))
        props.curve_preset = preset_key
        props.curve_bidirectional = bidirectional

        ok, msg = _populate_ynd_from_curve(
            curve_obj,
            props,
            preset_key,
            bidirectional=bidirectional,
            preserve_existing=True,
            append_mode=True,
        )
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}

        col = _get_or_create_col(YND_COLLECTION)
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        _build_ynd_objects(props, col)

        curve_obj["ynd_type"] = "source_curve"
        curve_obj["ynd_curve_preset"] = preset_key
        curve_obj["ynd_curve_bidirectional"] = bidirectional
        self.report({"INFO"}, msg.replace("Generated", "Synced"))
        return {"FINISHED"}


class YND_OT_UpdateLinksFromCurve(Operator):
    """Rebuild only adjacency links from the source curve and preserve manual extras"""
    bl_idname = "gta5_ynd.update_links_from_curve"; bl_label = "Update Links from Curve"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _find_ynd_source_curve(context) is not None

    def execute(self, context):
        curve_obj = _find_ynd_source_curve(context)
        if curve_obj is None:
            self.report({"WARNING"}, "No YND source curve found.")
            return {"CANCELLED"}

        props = context.scene.gta5_pathing.ynd
        preset_key = curve_obj.get("ynd_curve_preset", props.curve_preset)
        bidirectional = bool(curve_obj.get("ynd_curve_bidirectional", props.curve_bidirectional))
        props.curve_preset = preset_key
        props.curve_bidirectional = bidirectional
        ok, msg = _update_curve_links_only(curve_obj, props, preset_key, bidirectional=bidirectional)
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}

        _update_ynd_stats(props)
        _refresh_ynd_link_objects(props)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class YND_OT_SetOneWay(Operator):
    """Make the active node one-way by removing reverse links targeting it"""
    bl_idname = "gta5_ynd.set_one_way"; bl_label = "Set One-Way Links"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        p = context.scene.gta5_pathing.ynd
        return 0 <= p.node_index < len(p.nodes)

    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        node = props.nodes[props.node_index]
        removed = _remove_links_targeting_node(props, node.area_id, node.node_id)
        _refresh_ynd_link_objects(props)
        self.report({"INFO"}, f"{removed} reverse link(s) removed - node is now one-way")
        return {"FINISHED"}


class YND_OT_RecalcLinkLengths(Operator):
    """Recalculate all YND link lengths from current node positions"""
    bl_idname = "gta5_ynd.recalc_link_lengths"; bl_label = "Recalculate Link Lengths"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        recalc = _recalc_all_link_lengths(props)
        _refresh_ynd_link_objects(props)
        self.report({"INFO"}, f"{recalc} link length(s) recalculated")
        return {"FINISHED"}


class YND_OT_ApplyRoadPreset(Operator):
    """Apply the selected YND preset to the active node and its links"""
    bl_idname = "gta5_ynd.apply_road_preset"; bl_label = "Apply Road Preset"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        p = context.scene.gta5_pathing.ynd
        return 0 <= p.node_index < len(p.nodes)

    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        node = props.nodes[props.node_index]
        preset_key = props.curve_preset
        _apply_node_flags(node, *_preset_node_flags(preset_key, 0, 2))
        for link_index, link in enumerate(node.links):
            _apply_link_flags(link, *_preset_link_flags(preset_key, link_index, link_index + 1, max(2, len(node.links) + 1)))
        self.report({"INFO"}, f"Preset '{preset_key}' applied to node {node.area_id}:{node.node_id}")
        return {"FINISHED"}


class YND_OT_SyncFromObjects(Operator):
    """Syncs node positions from Blender empties"""
    bl_idname = "gta5_ynd.sync_from_objects"; bl_label = "Sync from Objects"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        count, stale = _sync_positions_from_node_objects(context, props)
        msg = f"{count} nodes synced"
        if stale:
            msg += f" ({stale} stale object(s) ignored)"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class YND_OT_RepairLocalIds(Operator):
    """Repairs duplicate node IDs in current YND and cleans local invalid links"""
    bl_idname = "gta5_ynd.repair_local_ids"; bl_label = "Repair Local IDs"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        changed = _repair_duplicate_local_ids(props)
        removed = _prune_invalid_local_links(props)

        # Refresh node object custom properties.
        for obj in context.scene.objects:
            if obj.get("ynd_type") != "node":
                continue
            idx = obj.get("node_index", -1)
            if 0 <= idx < len(props.nodes):
                n = props.nodes[idx]
                obj["node_area_id"] = n.area_id
                obj["node_id"] = n.node_id

        _refresh_ynd_link_objects(props)

        msg = f"Repair done: {changed} duplicate ID(s) fixed, {removed} local invalid link(s) removed"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class YND_OT_ValidateYND(Operator):
    """Validate current YND data and report issues without modifying anything"""
    bl_idname = "gta5_ynd.validate"; bl_label = "Validate YND"
    bl_options = {"REGISTER"}

    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        nodes = props.nodes
        issues = []

        # Duplicate (area_id, node_id)
        seen = {}
        for i, n in enumerate(nodes):
            key = (int(n.area_id), int(n.node_id))
            if key in seen:
                issues.append(f"Duplicate node ID {n.area_id}:{n.node_id} at indices {seen[key]} and {i}")
            else:
                seen[key] = i

        # Per-area id sets for local link validation
        ids_by_area = {}
        for n in nodes:
            ids_by_area.setdefault(int(n.area_id), set()).add(int(n.node_id))

        for i, n in enumerate(nodes):
            for j, lk in enumerate(n.links):
                # Self-link
                if int(lk.to_area_id) == int(n.area_id) and int(lk.to_node_id) == int(n.node_id):
                    issues.append(f"Node {n.area_id}:{n.node_id} link[{j}] is a self-link")
                # Broken local link
                elif int(lk.to_area_id) == int(n.area_id):
                    if int(lk.to_node_id) not in ids_by_area.get(int(n.area_id), set()):
                        issues.append(f"Node {n.area_id}:{n.node_id} link[{j}] → missing local target {lk.to_area_id}:{lk.to_node_id}")
                # Length out of valid range
                if not (1 <= int(lk.link_length) <= 255):
                    issues.append(f"Node {n.area_id}:{n.node_id} link[{j}] length {lk.link_length} out of [1..255]")

        if issues:
            for msg in issues[:10]:
                self.report({"WARNING"}, msg)
            if len(issues) > 10:
                self.report({"WARNING"}, f"... and {len(issues) - 10} more issue(s)")
            self.report({"INFO"}, f"Validation: {len(issues)} issue(s) found")
        else:
            self.report({"INFO"}, f"Validation passed — {len(nodes)} nodes, no issues")
        return {"FINISHED"}


_classes = [
    YND_OT_New,
    YND_OT_Import, YND_OT_Export,
    YND_OT_AddVehicleNode, YND_OT_AddPedNode, YND_OT_RemoveNode,
    YND_OT_AddLink, YND_OT_RemoveLink, YND_OT_RemoveAllLinks,
    YND_OT_LinkTwoNodes, YND_OT_GenerateFromCurve, YND_OT_SyncFromCurve, YND_OT_UpdateLinksFromCurve, YND_OT_SetOneWay,
    YND_OT_RecalcLinkLengths, YND_OT_ApplyRoadPreset, YND_OT_SyncFromObjects, YND_OT_RepairLocalIds,
    YND_OT_ValidateYND,
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
