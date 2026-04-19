"""
operators_ynd.py — Complete PathNodes YND with structured flags (ynd reference).
Import/Export XML, full node/link management, auto ped/vehicle detection.
"""
import bpy, bmesh, xml.etree.ElementTree as ET, math, os
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty, IntProperty
from mathutils import Vector
from .xml_utils import fval, ival, sval, sub_val, sub_text, to_xml_string
from .properties import PED_SPECIAL_TYPES

YND_COLLECTION = "YND_PathNodes"


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS FLAGS I/O
# ─────────────────────────────────────────────────────────────────────────────

def _apply_node_flags(
    n: "bpy.types.PropertyGroup",
    f0: int, f1: int, f2: int, f3: int, f4: int, f5: int,
) -> None:
    """Decode 6 raw flag bytes into the node's PropertyGroup sub-groups."""
    n.flags0.from_int(f0)
    n.flags1.from_int(f1)
    n.flags2.from_int(f2)
    n.flags3.from_int(f3)
    n.flags4.from_int(f4)
    n.flags5.from_int(f5)
    # Keep raw mirrors for potential low-level I/O access.
    n.raw0 = f0; n.raw1 = f1; n.raw2 = f2
    n.raw3 = f3; n.raw4 = f4; n.raw5 = f5


def _node_flags_to_ints(n):
    """Convert PropertyGroups back to 6 ints for XML export."""
    f0 = n.flags0.to_int()
    f1 = n.flags1.to_int()
    f2 = n.flags2.to_int()
    f3 = n.flags3.to_int()
    f4 = n.flags4.to_int()
    f5 = n.flags5.to_int()
    return f0, f1, f2, f3, f4, f5


def _apply_link_flags(lk: "bpy.types.PropertyGroup", f0: int, f1: int, f2: int) -> None:
    """Decode 3 raw flag bytes into the link's PropertyGroup sub-groups."""
    lk.flags0.from_int(f0)
    lk.flags1.from_int(f1)
    lk.flags2.from_int(f2)
    lk.raw_flags0 = f0; lk.raw_flags1 = f1; lk.raw_flags2 = f2


def _link_flags_to_ints(lk):
    return lk.flags0.to_int(), lk.flags1.to_int(), lk.flags2.to_int()


def _node_is_vehicle(n):
    return n.flags1.special_type not in PED_SPECIAL_TYPES


def _node_is_freeway(n):
    return n.flags2.freeway

def _node_is_junction(n):
    return n.flags2.junction


def _update_ynd_stats(props: "bpy.types.PropertyGroup") -> None:
    """Recompute all YND_Props stat counters from the current node list."""
    nodes = props.nodes
    props.stat_nodes     = len(nodes)
    props.stat_vehicle   = sum(1 for n in nodes if _node_is_vehicle(n))
    props.stat_ped       = sum(1 for n in nodes if not _node_is_vehicle(n))
    props.stat_junctions = sum(1 for n in nodes if _node_is_junction(n))


# ─────────────────────────────────────────────────────────────────────────────
#  PARSE XML
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ynd_xml(filepath, props):
    props.nodes.clear()
    try:
        tree = ET.parse(filepath)
    except ET.ParseError as e:
        return False, str(e)
    root = tree.getroot()
    if root.tag != "NodeDictionary":
        return False, f"Expected NodeDictionary root, found {root.tag}"

    nodes_el = root.find("Nodes")
    if nodes_el is not None:
        for node_el in nodes_el.findall("Item"):
            n = props.nodes.add()
            n.area_id    = ival(node_el, "AreaID",  400)
            n.node_id    = ival(node_el, "NodeID",  0)
            n.street_name= sval(node_el, "StreetName", "")
            f0 = ival(node_el, "Flags0", 2)
            f1 = ival(node_el, "Flags1", 0)
            f2 = ival(node_el, "Flags2", 0)
            f3 = ival(node_el, "Flags3", 64)
            f4 = ival(node_el, "Flags4", 134)
            f5 = ival(node_el, "Flags5", 2)
            pos = node_el.find("Position")
            if pos is not None:
                n.position = (float(pos.get("x",0)), float(pos.get("y",0)), float(pos.get("z",0)))
            _apply_node_flags(n, f0, f1, f2, f3, f4, f5)
            links_el = node_el.find("Links")
            if links_el is not None:
                for link_el in links_el.findall("Item"):
                    lk = n.links.add()
                    lk.to_area_id  = ival(link_el, "ToAreaID",   n.area_id)
                    lk.to_node_id  = ival(link_el, "ToNodeID",   0)
                    lk.link_length = ival(link_el, "LinkLength", 10)
                    lf0 = ival(link_el, "Flags0", 0)
                    lf1 = ival(link_el, "Flags1", 0)
                    lf2 = ival(link_el, "Flags2", 0)
                    _apply_link_flags(lk, lf0, lf1, lf2)

    props.stat_nodes   = len(props.nodes)
    props.stat_vehicle = sum(1 for n in props.nodes if _node_is_vehicle(n))
    props.stat_ped     = sum(1 for n in props.nodes if not _node_is_vehicle(n))
    props.stat_junctions = sum(1 for n in props.nodes if _node_is_junction(n))
    return True, "OK"


# ─────────────────────────────────────────────────────────────────────────────
#  BLENDER OBJECTS
# ─────────────────────────────────────────────────────────────────────────────

def _get_or_create_col(name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col

def _link_obj(obj, col):
    for c in obj.users_collection: c.objects.unlink(obj)
    col.objects.link(obj)


def _find_node_by_area_id(nodes, area_id, node_id):
    for i, n in enumerate(nodes):
        if n.area_id == area_id and n.node_id == node_id:
            return i, n
    return None, None


def _next_free_node_id(nodes, area_id):
    """Return the smallest free node_id for a given area."""
    used = {int(n.node_id) for n in nodes if int(n.area_id) == int(area_id)}
    nid = 0
    while nid in used:
        nid += 1
    return nid


def _build_node_index_map(nodes):
    """Map (area_id, node_id) -> node index for stable object syncing."""
    index_map = {}
    for i, n in enumerate(nodes):
        index_map[(int(n.area_id), int(n.node_id))] = i
    return index_map


def _find_node_index_for_object(obj, props, node_index_map):
    """Resolve node index from object custom props with stable-id fallback."""
    area = obj.get("node_area_id")
    node_id = obj.get("node_id")
    if area is not None and node_id is not None:
        idx = node_index_map.get((int(area), int(node_id)))
        if idx is not None:
            return idx

    idx = obj.get("node_index", -1)
    if 0 <= idx < len(props.nodes):
        n = props.nodes[idx]
        if area is None or node_id is None:
            return idx
        if int(n.area_id) == int(area) and int(n.node_id) == int(node_id):
            return idx

    return -1


def _sync_positions_from_node_objects(context, props):
    """Sync node positions from empties using stable identifiers.

    Returns (synced_count, stale_count).
    """
    node_index_map = _build_node_index_map(props.nodes)
    synced = 0
    stale = 0

    for obj in context.scene.objects:
        if obj.get("ynd_type") != "node":
            continue

        idx = _find_node_index_for_object(obj, props, node_index_map)
        if idx < 0:
            stale += 1
            continue

        node = props.nodes[idx]
        node.position = tuple(obj.location)

        # Keep custom properties aligned for future operations.
        obj["node_index"] = idx
        obj["node_area_id"] = node.area_id
        obj["node_id"] = node.node_id
        synced += 1

    return synced, stale


def _prune_invalid_local_links(props):
    """Remove links that target missing nodes in the same AreaID.

    External links (to other AreaID values) are preserved.
    Returns number of removed links.
    """
    removed = 0
    node_ids_by_area = {}
    for n in props.nodes:
        node_ids_by_area.setdefault(int(n.area_id), set()).add(int(n.node_id))

    for n in props.nodes:
        local_ids = node_ids_by_area.get(int(n.area_id), set())
        bad_indices = [
            i for i, lk in enumerate(n.links)
            if int(lk.to_area_id) == int(n.area_id) and int(lk.to_node_id) not in local_ids
        ]
        for i in reversed(bad_indices):
            n.links.remove(i)
            removed += 1

    return removed


def _remove_links_targeting_node(props, area_id, node_id):
    """Remove every link in props that targets (area_id, node_id)."""
    removed = 0
    for n in props.nodes:
        idxs = [
            i for i, lk in enumerate(n.links)
            if int(lk.to_area_id) == int(area_id) and int(lk.to_node_id) == int(node_id)
        ]
        for i in reversed(idxs):
            n.links.remove(i)
            removed += 1
    return removed


def _repair_duplicate_local_ids(props):
    """Ensure node_id uniqueness per area by reassigning duplicate IDs.

    Returns number of changed node IDs.
    """
    used_by_area = {}
    changed = 0

    for n in props.nodes:
        area = int(n.area_id)
        nid = int(n.node_id)
        used = used_by_area.setdefault(area, set())
        if nid in used:
            new_id = 0
            while new_id in used:
                new_id += 1
            n.node_id = new_id
            nid = new_id
            changed += 1
        used.add(nid)

    return changed


def _build_ynd_link_objects(props, col):
    root_links = bpy.data.objects.new("YND_Links", None)
    root_links.empty_display_type = "PLAIN_AXES"
    root_links.empty_display_size = 0.1
    root_links["ynd_type"] = "links_root"
    _link_obj(root_links, col)

    for src_index, node in enumerate(props.nodes):
        start = node.position
        for link_index, lk in enumerate(node.links):
            target_index, target_node = _find_node_by_area_id(props.nodes, lk.to_area_id, lk.to_node_id)
            if target_node is None:
                continue
            curve_data = bpy.data.curves.new(f"YND_LinkCurve_{src_index}_{link_index}", type="CURVE")
            curve_data.dimensions = "3D"
            curve_data.resolution_u = 2
            curve_data.bevel_depth = 0.02
            curve_data.bevel_resolution = 0
            spline = curve_data.splines.new("POLY")
            spline.points.add(1)
            spline.points[0].co = (*start, 1.0)
            spline.points[1].co = (*target_node.position, 1.0)
            obj = bpy.data.objects.new(f"YND_Link_{node.area_id}_{node.node_id}_{lk.to_area_id}_{lk.to_node_id}", curve_data)
            obj["ynd_type"] = "link"
            obj["link_from"] = src_index
            obj["link_to"] = target_index
            obj.parent = root_links
            _link_obj(obj, col)
    return root_links


def _refresh_ynd_link_objects(props):
    """Rebuild visual link objects from current props state."""
    col = bpy.data.collections.get(YND_COLLECTION)
    if col is None:
        return

    for obj in list(col.objects):
        if obj.get("ynd_type") in {"link", "links_root"}:
            bpy.data.objects.remove(obj, do_unlink=True)

    links_root = _build_ynd_link_objects(props, col)
    root_obj = next((o for o in col.objects if o.get("ynd_type") == "root"), None)
    if root_obj is not None:
        links_root.parent = root_obj


def _build_ynd_objects(props, col):
    root_obj = bpy.data.objects.new("YND_Root", None)
    root_obj.empty_display_type = "PLAIN_AXES"
    root_obj.empty_display_size = 1.0
    root_obj["ynd_type"] = "root"
    _link_obj(root_obj, col)

    for i, node in enumerate(props.nodes):
        is_veh = _node_is_vehicle(node)
        obj = bpy.data.objects.new(
            f"YND_{'V' if is_veh else 'P'}_{node.area_id}_{node.node_id}_{node.street_name or 'unnamed'}",
            None
        )
        # Cubes for vehicles, spheres for pedestrians
        obj.empty_display_type = "CUBE" if is_veh else "SPHERE"
        obj.empty_display_size = 0.5 if is_veh else 0.3
        obj.location = node.position
        obj.lock_rotation = (True, True, True)
        obj.lock_scale    = (True, True, True)
        obj["ynd_type"]      = "node"
        obj["node_index"]    = i
        obj["node_area_id"]  = node.area_id
        obj["node_id"]       = node.node_id
        obj["street_name"]   = node.street_name
        obj["is_vehicle"]    = is_veh
        obj["is_freeway"]    = _node_is_freeway(node)
        obj["is_junction"]   = _node_is_junction(node)
        obj.parent = root_obj
        _link_obj(obj, col)

    links_root = _build_ynd_link_objects(props, col)
    links_root.parent = root_obj
    return root_obj


# ─────────────────────────────────────────────────────────────────────────────
#  EXPORT XML
# ─────────────────────────────────────────────────────────────────────────────

def _build_ynd_xml(context, props):
    # Sync positions from empties with stable IDs.
    _sync_positions_from_node_objects(context, props)
    _prune_invalid_local_links(props)

    root = ET.Element("NodeDictionary")
    sub_val(root, "VehicleNodeCount", sum(1 for n in props.nodes if _node_is_vehicle(n)))
    sub_val(root, "PedNodeCount",     sum(1 for n in props.nodes if not _node_is_vehicle(n)))

    nodes_el = ET.SubElement(root, "Nodes")
    for node in props.nodes:
        item = ET.SubElement(nodes_el, "Item")
        sub_val(item, "AreaID", node.area_id)
        sub_val(item, "NodeID", node.node_id)
        ET.SubElement(item, "StreetName").text = node.street_name
        pos = ET.SubElement(item, "Position")
        pos.set("x", f"{node.position[0]:.6f}")
        pos.set("y", f"{node.position[1]:.6f}")
        pos.set("z", f"{node.position[2]:.6f}")
        f0, f1, f2, f3, f4, f5 = _node_flags_to_ints(node)
        for fi, fv in enumerate([f0,f1,f2,f3,f4,f5]):
            sub_val(item, f"Flags{fi}", fv)
        links_el = ET.SubElement(item, "Links")
        for lk in node.links:
            litem = ET.SubElement(links_el, "Item")
            sub_val(litem, "ToAreaID",   lk.to_area_id)
            sub_val(litem, "ToNodeID",   lk.to_node_id)
            lf0, lf1, lf2 = _link_flags_to_ints(lk)
            sub_val(litem, "Flags0", lf0)
            sub_val(litem, "Flags1", lf1)
            sub_val(litem, "Flags2", lf2)
            sub_val(litem, "LinkLength", lk.link_length)

    ET.SubElement(root, "Junctions")
    return to_xml_string(root)


# ─────────────────────────────────────────────────────────────────────────────
#  OPÉRATEURS
# ─────────────────────────────────────────────────────────────────────────────

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
        if not ok: self.report({"ERROR"}, msg); return {"CANCELLED"}
        props.filepath = self.filepath
        col = _get_or_create_col(YND_COLLECTION)
        for obj in list(col.objects): bpy.data.objects.remove(obj, do_unlink=True)
        _build_ynd_objects(props, col)
        self.report({"INFO"},
            f"YND imported: {props.stat_vehicle} vehicle, "
            f"{props.stat_ped} ped, {props.stat_junctions} junctions")
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


_classes = [
    YND_OT_Import, YND_OT_Export,
    YND_OT_AddVehicleNode, YND_OT_AddPedNode, YND_OT_RemoveNode,
    YND_OT_AddLink, YND_OT_RemoveLink, YND_OT_RemoveAllLinks,
    YND_OT_LinkTwoNodes, YND_OT_SyncFromObjects, YND_OT_RepairLocalIds,
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
