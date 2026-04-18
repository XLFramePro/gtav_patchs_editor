"""
ops_ynd.py — PathNodes YND v4.1

FIXES:
  ✅ NodeID renumbering after deletion (prevents CW corruption)
  ✅ JunctionRefs cleaned up on node delete  
  ✅ Parent Empty hierarchy per imported file
  ✅ Proper _pos_x/y/z update after reindex
  ✅ All-in-one collection per file
"""
import bpy, xml.etree.ElementTree as ET, math, os
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty, IntProperty
from mathutils import Vector
from .xmlio import geti, gets, seti, to_xml_string
from .props import PED_SPECIAL_TYPES

# ── Constants ─────────────────────────────────────────────────────────────────
_COL_PREFIX = "GTA5PE_YND_"   # each imported file gets its own collection

# ── Collection / parent helpers ───────────────────────────────────────────────

def _get_or_create_col(name):
    col = bpy.data.collections.get(name)
    if not col:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col

def _link(obj, col):
    for c in obj.users_collection: c.objects.unlink(obj)
    col.objects.link(obj)

def _clear_col(col_name):
    col = bpy.data.collections.get(col_name)
    if col:
        for o in list(col.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(col)

def _get_ynd_col(props):
    """Return (or create) the collection for this YND file."""
    label = props.get("col_name", _COL_PREFIX + "default")
    return _get_or_create_col(label)

# ── Flag helpers ──────────────────────────────────────────────────────────────

def _apply_flags(n, f0, f1, f2, f3, f4, f5):
    n.nf0.from_int(f0); n.nf1.from_int(f1); n.nf2.from_int(f2)
    n.nf3.from_int(f3); n.nf4.from_int(f4); n.nf5.from_int(f5)

def _flags_to_ints(n):
    return (n.nf0.to_int(), n.nf1.to_int(), n.nf2.to_int(),
            n.nf3.to_int(), n.nf4.to_int(), n.nf5.to_int())

def _is_veh(n):  return n.nf1.special_type not in PED_SPECIAL_TYPES
def _is_jct(n):  return bool(n.nf2.junction)

def _dist(a, b):
    return min(255, max(1, int(math.sqrt(
        (b[0]-a[0])**2 + (b[1]-a[1])**2 + (b[2]-a[2])**2))))

def _update_stats(props):
    props.stat_total   = len(props.nodes)
    props.stat_vehicle = sum(1 for n in props.nodes if _is_veh(n))
    props.stat_ped     = sum(1 for n in props.nodes if not _is_veh(n))
    props.stat_jct     = len(props.junctions)

# ── Parse XML ─────────────────────────────────────────────────────────────────

def _parse(filepath, props):
    props.nodes.clear()
    props.junctions.clear()
    props.junction_refs.clear()
    try:
        root = ET.parse(filepath).getroot()
    except Exception as e:
        return False, str(e)
    if root.tag != "NodeDictionary":
        return False, f"Expected NodeDictionary, got {root.tag}"

    for node_el in (root.find("Nodes") or []):
        n = props.nodes.add()
        n.area_id     = geti(node_el, "AreaID",    400)
        n.node_id     = geti(node_el, "NodeID",    0)
        n.street_name = gets(node_el, "StreetName","")
        pos = node_el.find("Position")
        if pos is not None:
            n.pos_x_str = pos.get("x", "0")
            n.pos_y_str = pos.get("y", "0")
            n.pos_z_str = pos.get("z", "0")
            n.position  = (float(n.pos_x_str), float(n.pos_y_str), float(n.pos_z_str))
        _apply_flags(n,
            geti(node_el,"Flags0",2),   geti(node_el,"Flags1",0),
            geti(node_el,"Flags2",0),   geti(node_el,"Flags3",64),
            geti(node_el,"Flags4",134), geti(node_el,"Flags5",2))
        for lk_el in (node_el.find("Links") or []):
            lk = n.links.add()
            lk.to_area_id  = geti(lk_el, "ToAreaID",   n.area_id)
            lk.to_node_id  = geti(lk_el, "ToNodeID",   0)
            lk.link_length = geti(lk_el, "LinkLength",  10)
            lk.lf0.from_int(geti(lk_el, "Flags0", 0))
            lk.lf1.from_int(geti(lk_el, "Flags1", 0))
            lk.lf2.from_int(geti(lk_el, "Flags2", 0))

    for jct_el in (root.find("Junctions") or []):
        j = props.junctions.add()
        pos = jct_el.find("Position")
        if pos is not None:
            j.pos_x = pos.get("x", "0"); j.pos_y = pos.get("y", "0")
        j.min_z  = jct_el.find("MinZ").get("value","0")  if jct_el.find("MinZ")  else "0"
        j.max_z  = jct_el.find("MaxZ").get("value","0")  if jct_el.find("MaxZ")  else "0"
        j.size_x = jct_el.find("SizeX").get("value","0") if jct_el.find("SizeX") else "0"
        j.size_y = jct_el.find("SizeY").get("value","0") if jct_el.find("SizeY") else "0"
        hm = jct_el.find("Heightmap")
        j.heightmap = hm.text if hm is not None and hm.text else ""

    for ref_el in (root.find("JunctionRefs") or []):
        r = props.junction_refs.add()
        r.area_id     = geti(ref_el, "AreaID",     0)
        r.node_id     = geti(ref_el, "NodeID",     0)
        r.junction_id = geti(ref_el, "JunctionID", 0)
        r.unk0        = geti(ref_el, "Unk0",        0)

    _update_stats(props)
    return True, "OK"

# ── Build objects (parent empty hierarchy) ────────────────────────────────────

def _make_root_empty(filename, col):
    """Create the root empty named after the file."""
    obj = bpy.data.objects.new(filename, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.01
    obj["ynd_type"] = "root"
    obj["ynd_file"] = filename
    _link(obj, col)
    return obj

def _make_node_obj(nd, i, col, parent):
    is_veh = _is_veh(nd)
    label  = f"YND_{'V' if is_veh else 'P'}_{nd.area_id}_{nd.node_id}"
    if nd.street_name: label += f"_{nd.street_name[:10]}"
    obj = bpy.data.objects.new(label, None)
    obj.empty_display_type = "CUBE"   if is_veh else "SPHERE"
    obj.empty_display_size = 0.5      if is_veh else 0.3
    obj.location           = (nd.position[0], nd.position[1], nd.position[2])
    obj.lock_rotation      = (True, True, True)
    obj.lock_scale         = (True, True, True)
    if parent:
        obj.parent = parent
    obj["ynd_type"] = "node"
    obj["node_idx"] = i
    obj["area_id"]  = nd.area_id
    obj["node_id"]  = nd.node_id
    obj["_pos_x"]   = nd.pos_x_str or f"{nd.position[0]:.7g}"
    obj["_pos_y"]   = nd.pos_y_str or f"{nd.position[1]:.7g}"
    obj["_pos_z"]   = nd.pos_z_str or f"{nd.position[2]:.7g}"
    _link(obj, col)
    return obj

def _build_objects(props, col, root_empty):
    for i, nd in enumerate(props.nodes):
        _make_node_obj(nd, i, col, root_empty)

# ── Node renumbering ──────────────────────────────────────────────────────────

def _renumber_nodes(props, col):
    """After deletion: renumber NodeIDs to be sequential 0..N-1
    and update all links + JunctionRefs accordingly."""
    # Build old_node_id → new_node_id mapping (within same area)
    # We only renumber nodes within the same area_id
    area_counter = {}
    id_remap = {}   # (area_id, old_node_id) → new_node_id

    for nd in props.nodes:
        area = nd.area_id
        new_id = area_counter.get(area, 0)
        id_remap[(area, nd.node_id)] = new_id
        area_counter[area] = new_id + 1

    # Apply new NodeIDs to nodes
    for nd in props.nodes:
        old_id = nd.node_id
        new_id = id_remap.get((nd.area_id, old_id), old_id)
        nd.node_id = new_id

    # Update links
    for nd in props.nodes:
        for lk in nd.links:
            new_target = id_remap.get((lk.to_area_id, lk.to_node_id))
            if new_target is not None:
                lk.to_node_id = new_target

    # Update JunctionRefs
    for ref in props.junction_refs:
        new_id = id_remap.get((ref.area_id, ref.node_id))
        if new_id is not None:
            ref.node_id = new_id
        else:
            # Ref points to deleted node: mark for removal
            ref.node_id = -1

    # Remove orphaned JunctionRefs
    for i in reversed(range(len(props.junction_refs))):
        if props.junction_refs[i].node_id < 0:
            props.junction_refs.remove(i)

    # Update node_id on Blender objects
    if col:
        for obj in col.objects:
            if obj.get("ynd_type") == "node":
                area = obj.get("area_id", -1)
                old  = obj.get("node_id",  -1)
                new  = id_remap.get((area, old), old)
                obj["node_id"] = new
                # Update label
                is_veh = obj.empty_display_type == "CUBE"
                street = ""
                idx = obj.get("node_idx", -1)
                if 0 <= idx < len(props.nodes):
                    street = props.nodes[idx].street_name[:10] if props.nodes[idx].street_name else ""
                prefix = "V" if is_veh else "P"
                new_name = f"YND_{prefix}_{area}_{new}"
                if street: new_name += f"_{street}"
                obj.name = new_name

# ── Export ────────────────────────────────────────────────────────────────────

def _export(props):
    # Read exact positions from Blender objects
    col_name = props.get("col_name", "")
    col = bpy.data.collections.get(col_name) if col_name else None
    obj_pos = {}
    if col:
        for obj in col.objects:
            if obj.get("ynd_type") == "node":
                idx = obj.get("node_idx", -1)
                if idx >= 0:
                    px = obj.get("_pos_x", "")
                    py = obj.get("_pos_y", "")
                    pz = obj.get("_pos_z", "")
                    if px and py and pz:
                        obj_pos[idx] = (px, py, pz)

    root = ET.Element("NodeDictionary")
    seti(root, "VehicleNodeCount", sum(1 for n in props.nodes if _is_veh(n)))
    seti(root, "PedNodeCount",     sum(1 for n in props.nodes if not _is_veh(n)))

    nodes_el = ET.SubElement(root, "Nodes")
    for i, nd in enumerate(props.nodes):
        item = ET.SubElement(nodes_el, "Item")
        seti(item, "AreaID",  nd.area_id)
        seti(item, "NodeID",  nd.node_id)
        ET.SubElement(item, "StreetName").text = nd.street_name
        pos = ET.SubElement(item, "Position")
        if i in obj_pos:
            px, py, pz = obj_pos[i]
        else:
            px = nd.pos_x_str or f"{nd.position[0]:.7g}"
            py = nd.pos_y_str or f"{nd.position[1]:.7g}"
            pz = nd.pos_z_str or f"{nd.position[2]:.7g}"
        pos.set("x", px); pos.set("y", py); pos.set("z", pz)
        for fi, fv in enumerate(_flags_to_ints(nd)):
            seti(item, f"Flags{fi}", fv)
        lks_el = ET.SubElement(item, "Links")
        for lk in nd.links:
            li = ET.SubElement(lks_el, "Item")
            seti(li, "ToAreaID",   lk.to_area_id)
            seti(li, "ToNodeID",   lk.to_node_id)
            seti(li, "Flags0",     lk.lf0.to_int())
            seti(li, "Flags1",     lk.lf1.to_int())
            seti(li, "Flags2",     lk.lf2.to_int())
            seti(li, "LinkLength", lk.link_length)

    jcts_el = ET.SubElement(root, "Junctions")
    for j in props.junctions:
        item = ET.SubElement(jcts_el, "Item")
        pos = ET.SubElement(item, "Position")
        pos.set("x", j.pos_x); pos.set("y", j.pos_y)
        ET.SubElement(item, "MinZ").set("value",  j.min_z)
        ET.SubElement(item, "MaxZ").set("value",  j.max_z)
        ET.SubElement(item, "SizeX").set("value", j.size_x)
        ET.SubElement(item, "SizeY").set("value", j.size_y)
        hm = ET.SubElement(item, "Heightmap")
        hm.text = j.heightmap or ""

    refs_el = ET.SubElement(root, "JunctionRefs")
    for r in props.junction_refs:
        item = ET.SubElement(refs_el, "Item")
        seti(item, "AreaID",     r.area_id)
        seti(item, "NodeID",     r.node_id)
        seti(item, "JunctionID", r.junction_id)
        seti(item, "Unk0",       r.unk0)

    return to_xml_string(root)

# ── Sync ──────────────────────────────────────────────────────────────────────

def _sync_from_objects(props):
    col_name = props.get("col_name", "")
    col = bpy.data.collections.get(col_name) if col_name else None
    if col is None: return 0
    count = 0
    for obj in col.objects:
        if obj.get("ynd_type") != "node": continue
        idx = obj.get("node_idx", -1)
        if 0 <= idx < len(props.nodes):
            x, y, z = obj.location[0], obj.location[1], obj.location[2]
            nd = props.nodes[idx]
            nd.position  = (x, y, z)
            px = f"{x:.7g}"; py = f"{y:.7g}"; pz = f"{z:.7g}"
            nd.pos_x_str = px; nd.pos_y_str = py; nd.pos_z_str = pz
            obj["_pos_x"] = px; obj["_pos_y"] = py; obj["_pos_z"] = pz
            count += 1
    return count

def _remove_node_and_links(props, idx):
    if not (0 <= idx < len(props.nodes)): return
    nd = props.nodes[idx]
    r_area, r_id = nd.area_id, nd.node_id
    for n in props.nodes:
        to_rem = [i for i, lk in enumerate(n.links)
                  if lk.to_area_id == r_area and lk.to_node_id == r_id]
        for i in reversed(to_rem): n.links.remove(i)
    props.nodes.remove(idx)
    props.node_idx = max(0, min(props.node_idx, len(props.nodes) - 1))

# ── OPERATORS ────────────────────────────────────────────────────────────────

class YND_OT_Import(Operator):
    """Import a YND XML PathNodes file (nodes + junctions + refs)"""
    bl_idname = "gta5pe.ynd_import"; bl_label = "Import YND"
    bl_options = {"REGISTER", "UNDO"}
    filepath:    StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.xml;*.ynd.xml", options={"HIDDEN"})

    def invoke(self, ctx, e):
        ctx.window_manager.fileselect_add(self); return {"RUNNING_MODAL"}

    def execute(self, ctx):
        props    = ctx.scene.gta5pe.ynd
        filename = os.path.basename(self.filepath)
        col_name = _COL_PREFIX + os.path.splitext(filename)[0]

        ok, msg = _parse(self.filepath, props)
        if not ok: self.report({"ERROR"}, msg); return {"CANCELLED"}

        props.filepath   = self.filepath
        props["col_name"]= col_name

        # Clear previous collection of same name
        old = bpy.data.collections.get(col_name)
        if old:
            for o in list(old.objects): bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(old)

        col = _get_or_create_col(col_name)
        root_empty = _make_root_empty(filename, col)
        _build_objects(props, col, root_empty)
        _update_stats(props)

        self.report({"INFO"},
            f"YND: {props.stat_vehicle} veh | {props.stat_ped} ped | {props.stat_jct} junctions")
        return {"FINISHED"}


class YND_OT_New(Operator):
    """Create an empty NodeDictionary"""
    bl_idname = "gta5pe.ynd_new"; bl_label = "New YND"
    bl_options = {"REGISTER", "UNDO"}
    area_id: IntProperty(name="Area ID", default=400, min=0)
    filename: StringProperty(name="Filename", default="new_nodes")

    def invoke(self, ctx, e): return ctx.window_manager.invoke_props_dialog(self)

    def execute(self, ctx):
        props = ctx.scene.gta5pe.ynd
        props.nodes.clear(); props.junctions.clear(); props.junction_refs.clear()
        props.filepath = ""; props.area_id = self.area_id
        col_name = _COL_PREFIX + self.filename
        props["col_name"] = col_name
        old = bpy.data.collections.get(col_name)
        if old:
            for o in list(old.objects): bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(old)
        col = _get_or_create_col(col_name)
        _make_root_empty(self.filename + ".ynd", col)
        _update_stats(props)
        self.report({"INFO"}, f"New YND — Area {self.area_id}")
        return {"FINISHED"}


class YND_OT_Export(Operator):
    """Export PathNodes to YND XML (nodes + junctions + refs)"""
    bl_idname = "gta5pe.ynd_export"; bl_label = "Export YND"
    bl_options = {"REGISTER"}
    filepath:    StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.xml", options={"HIDDEN"})

    def invoke(self, ctx, e):
        self.filepath = ctx.scene.gta5pe.ynd.filepath or "nodes.ynd.xml"
        ctx.window_manager.fileselect_add(self); return {"RUNNING_MODAL"}

    def execute(self, ctx):
        props = ctx.scene.gta5pe.ynd
        xml   = _export(props)
        try:
            with open(self.filepath, "w", encoding="utf-8") as f: f.write(xml)
        except OSError as e:
            self.report({"ERROR"}, str(e)); return {"CANCELLED"}
        props.filepath = self.filepath
        self.report({"INFO"},
            f"YND exported: {props.stat_total} nodes, {len(props.junctions)} junctions → {self.filepath}")
        return {"FINISHED"}


class YND_OT_AddVehicle(Operator):
    """Add a vehicle node at the 3D cursor"""
    bl_idname = "gta5pe.ynd_add_veh"; bl_label = "Add Vehicle Node"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, ctx):
        props = ctx.scene.gta5pe.ynd
        n = props.nodes.add()
        n.area_id = props.area_id
        n.node_id = len(props.nodes) - 1
        loc = ctx.scene.cursor.location
        n.position  = tuple(loc)
        n.pos_x_str = f"{loc.x:.7g}"; n.pos_y_str = f"{loc.y:.7g}"; n.pos_z_str = f"{loc.z:.7g}"
        _apply_flags(n, 2, 0, 0, 64, 134, 2)
        props.node_idx = len(props.nodes) - 1
        _update_stats(props)
        col = bpy.data.collections.get(props.get("col_name", ""))
        if not col: col = _get_or_create_col(_COL_PREFIX + "default")
        # Find parent empty
        parent = next((o for o in col.objects if o.get("ynd_type") == "root"), None)
        _make_node_obj(n, props.node_idx, col, parent)
        return {"FINISHED"}


class YND_OT_AddPed(Operator):
    """Add a pedestrian node at the 3D cursor"""
    bl_idname = "gta5pe.ynd_add_ped"; bl_label = "Add Ped Node"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, ctx):
        props = ctx.scene.gta5pe.ynd
        n = props.nodes.add()
        n.area_id = props.area_id
        n.node_id = len(props.nodes) - 1
        loc = ctx.scene.cursor.location
        n.position  = tuple(loc)
        n.pos_x_str = f"{loc.x:.7g}"; n.pos_y_str = f"{loc.y:.7g}"; n.pos_z_str = f"{loc.z:.7g}"
        _apply_flags(n, 2, 80, 0, 8, 2, 2)
        props.node_idx = len(props.nodes) - 1
        _update_stats(props)
        col = bpy.data.collections.get(props.get("col_name", ""))
        if not col: col = _get_or_create_col(_COL_PREFIX + "default")
        parent = next((o for o in col.objects if o.get("ynd_type") == "root"), None)
        _make_node_obj(n, props.node_idx, col, parent)
        return {"FINISHED"}


class YND_OT_RemNode(Operator):
    """Delete active node + its Blender object + all incoming links.
    NodeIDs are renumbered to stay sequential (required by CodeWalker)."""
    bl_idname = "gta5pe.ynd_rem_node"; bl_label = "Delete Node"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, ctx):
        p = ctx.scene.gta5pe.ynd; return 0 <= p.node_idx < len(p.nodes)

    def execute(self, ctx):
        props    = ctx.scene.gta5pe.ynd
        idx      = props.node_idx
        col_name = props.get("col_name", "")
        col      = bpy.data.collections.get(col_name)

        # Remove Blender object
        if col:
            for obj in list(col.objects):
                if obj.get("ynd_type") == "node" and obj.get("node_idx") == idx:
                    bpy.data.objects.remove(obj, do_unlink=True); break

        # Remove node + incoming links
        _remove_node_and_links(props, idx)

        # Shift node_idx on remaining objects
        if col:
            for obj in col.objects:
                if obj.get("ynd_type") == "node":
                    cur = obj.get("node_idx", -1)
                    if cur > idx: obj["node_idx"] = cur - 1

        # Renumber NodeIDs to stay sequential → prevents CW corruption
        _renumber_nodes(props, col)

        _update_stats(props)
        self.report({"INFO"}, f"Node deleted. Renumbered {props.stat_total} nodes.")
        return {"FINISHED"}


class YND_OT_AddLink(Operator):
    """Add an outgoing link to the active node"""
    bl_idname = "gta5pe.ynd_add_link"; bl_label = "Add Link"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, ctx):
        p = ctx.scene.gta5pe.ynd; return 0 <= p.node_idx < len(p.nodes)

    def execute(self, ctx):
        props = ctx.scene.gta5pe.ynd; nd = props.nodes[props.node_idx]
        lk = nd.links.add(); lk.to_area_id = nd.area_id; lk.link_length = 10
        nd.link_idx = len(nd.links) - 1; return {"FINISHED"}


class YND_OT_RemLink(Operator):
    """Delete the active link"""
    bl_idname = "gta5pe.ynd_rem_link"; bl_label = "Delete Link"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, ctx):
        p = ctx.scene.gta5pe.ynd
        if not (0 <= p.node_idx < len(p.nodes)): return False
        return 0 <= p.nodes[p.node_idx].link_idx < len(p.nodes[p.node_idx].links)

    def execute(self, ctx):
        props = ctx.scene.gta5pe.ynd; nd = props.nodes[props.node_idx]
        nd.links.remove(nd.link_idx)
        nd.link_idx = min(nd.link_idx, len(nd.links) - 1); return {"FINISHED"}


class YND_OT_RemAllLinks(Operator):
    """Clear all links on the active node"""
    bl_idname = "gta5pe.ynd_rem_all_links"; bl_label = "Clear All Links"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, ctx):
        p = ctx.scene.gta5pe.ynd; return 0 <= p.node_idx < len(p.nodes)
    def invoke(self, ctx, e): return ctx.window_manager.invoke_confirm(self, e)

    def execute(self, ctx):
        props = ctx.scene.gta5pe.ynd; nd = props.nodes[props.node_idx]
        count = len(nd.links); nd.links.clear(); nd.link_idx = -1
        self.report({"INFO"}, f"{count} link(s) cleared"); return {"FINISHED"}


class YND_OT_LinkTo(Operator):
    """Create a link to a target node (auto length)"""
    bl_idname = "gta5pe.ynd_link_to"; bl_label = "Link To Node"
    bl_options = {"REGISTER", "UNDO"}
    target_area: IntProperty(name="Target Area ID", default=400, min=0)
    target_node: IntProperty(name="Target Node ID", default=0,   min=0)
    bidir:       BoolProperty(name="Bidirectional",  default=True)

    @classmethod
    def poll(cls, ctx):
        p = ctx.scene.gta5pe.ynd; return 0 <= p.node_idx < len(p.nodes)

    def invoke(self, ctx, e):
        self.target_area = ctx.scene.gta5pe.ynd.nodes[ctx.scene.gta5pe.ynd.node_idx].area_id
        return ctx.window_manager.invoke_props_dialog(self)

    def execute(self, ctx):
        props = ctx.scene.gta5pe.ynd; src = props.nodes[props.node_idx]
        tgt = next((n for n in props.nodes
                    if n.area_id == self.target_area and n.node_id == self.target_node), None)
        dist = _dist(src.position, tgt.position) if tgt else 10
        lk = src.links.add()
        lk.to_area_id = self.target_area; lk.to_node_id = self.target_node; lk.link_length = dist
        if self.bidir and tgt:
            lk2 = tgt.links.add()
            lk2.to_area_id = src.area_id; lk2.to_node_id = src.node_id; lk2.link_length = dist
        self.report({"INFO"}, f"Link {'↔' if self.bidir else '→'} created  L={dist}")
        return {"FINISHED"}


class YND_OT_Sync(Operator):
    """Sync positions from Blender empties → props (run before export if nodes were moved)"""
    bl_idname = "gta5pe.ynd_sync"; bl_label = "Sync Positions"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, ctx):
        props = ctx.scene.gta5pe.ynd
        count = _sync_from_objects(props)
        _update_stats(props)
        self.report({"INFO"}, f"{count} positions updated from Blender objects")
        return {"FINISHED"}


class YND_OT_TrackActive(Operator):
    """Modal: follow active object to update node_idx in panel."""
    bl_idname = "gta5pe.ynd_track_active"; bl_label = "Track Active YND Object"
    bl_options = set()
    _last = None

    def modal(self, ctx, event):
        if not hasattr(ctx.scene, "gta5pe"): return {"CANCELLED"}
        if ctx.scene.gta5pe.tab != "YND":    return {"PASS_THROUGH"}
        if event.type not in ("LEFTMOUSE", "MOUSEMOVE", "TIMER"): return {"PASS_THROUGH"}
        obj = ctx.active_object
        if obj is self.__class__._last: return {"PASS_THROUGH"}
        self.__class__._last = obj
        if obj and obj.get("ynd_type") == "node":
            idx   = obj.get("node_idx", -1)
            props = ctx.scene.gta5pe.ynd
            if 0 <= idx < len(props.nodes) and props.node_idx != idx:
                props.node_idx = idx
                for a in ctx.screen.areas: a.tag_redraw()
        return {"PASS_THROUGH"}

    def invoke(self, ctx, e):
        ctx.window_manager.modal_handler_add(self); return {"RUNNING_MODAL"}


_CLASSES = [
    YND_OT_Import, YND_OT_New, YND_OT_Export,
    YND_OT_AddVehicle, YND_OT_AddPed, YND_OT_RemNode,
    YND_OT_AddLink, YND_OT_RemLink, YND_OT_RemAllLinks,
    YND_OT_LinkTo, YND_OT_Sync, YND_OT_TrackActive,
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
