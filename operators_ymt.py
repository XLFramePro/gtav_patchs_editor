"""
operators_ymt.py — Scenarios YMT : export natif .ymt XML + gestion arêtes de chaînage.
Note importante : GTA5 utilise le format XML sérialisé. L'extension de fichier
sera .ymt.xml pour l'interopérabilité avec les outils de conversion (OpenIV, CodeWalker).
"""
import bpy, math, xml.etree.ElementTree as ET, os
from bpy.types import Operator
from bpy.props import StringProperty, IntProperty, BoolProperty
from mathutils import Vector
from .xml_utils import fval, ival, sval, bval, sub_val, sub_text, to_xml_string

YMT_COLLECTION = "YMT_Scenarios"

ITYPE_NAMES = {
    1:"walk", 3:"sit", 5:"drive", 6:"park", 7:"atm",
    10:"prone", 14:"no_spawn", 16:"guard", 18:"wander",
    20:"drinking", 21:"smoking",
}

SCENARIO_COLORS = {
    1:(0.8,0.8,0.2,1.0), 3:(0.2,0.8,0.2,1.0), 5:(0.1,0.5,1.0,1.0),
    6:(0.5,0.3,1.0,1.0), 7:(1.0,0.5,0.1,1.0), 14:(0.5,0.5,0.5,0.5),
    18:(0.8,0.2,0.8,1.0), "default":(0.9,0.9,0.9,1.0),
}


def _get_or_create_col(name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def _link_obj(obj, col):
    for c in obj.users_collection: c.objects.unlink(obj)
    col.objects.link(obj)


def _parse_ymt_xml(filepath, props):
    props.scenario_points.clear(); props.chaining_nodes.clear()
    props.chaining_edges.clear(); props.chains.clear()
    props.entity_overrides.clear()
    try:
        tree = ET.parse(filepath)
    except ET.ParseError as e:
        return False, str(e)
    root = tree.getroot()
    if root.tag != "CScenarioPointRegion":
        return False, f"Racine attendue CScenarioPointRegion, trouvée {root.tag}"
    props.version_number = ival(root, "VersionNumber", 80)
    points_section = root.find("Points")
    if points_section is not None:
        my_points = points_section.find("MyPoints")
        if my_points is not None:
            for item in my_points.findall("Item"):
                sp = props.scenario_points.add()
                sp.itype           = ival(item, "iType", 1)
                sp.model_set_id    = ival(item, "ModelSetId", 0)
                sp.interior_id     = ival(item, "iInterior", 0)
                sp.imap_id         = ival(item, "iRequiredIMapId", 0)
                sp.probability     = ival(item, "iProbability", 0)
                sp.avail_mp_sp     = ival(item, "uAvailableInMpSp", 1)
                sp.time_start      = ival(item, "iTimeStartOverride", 0)
                sp.time_end        = ival(item, "iTimeEndOverride", 24)
                sp.radius          = ival(item, "iRadius", 0)
                sp.time_till_leaves= ival(item, "iTimeTillPedLeaves", 255)
                sp.scenario_group  = ival(item, "iScenarioGroup", 0)
                flags_el = item.find("Flags")
                sp.flags = (flags_el.text or "").strip() if flags_el is not None else ""
                pos_el = item.find("vPositionAndDirection")
                if pos_el is not None:
                    sp.position = (float(pos_el.get("x",0)), float(pos_el.get("y",0)),
                                   float(pos_el.get("z",0)), float(pos_el.get("w",0)))
    eo_section = root.find("EntityOverrides")
    if eo_section is not None:
        for item in eo_section.findall("Item"):
            eo = props.entity_overrides.add()
            et_el = item.find("EntityType")
            eo.entity_type = (et_el.text or "").strip() if et_el is not None else ""
            ep_el = item.find("EntityPosition")
            if ep_el is not None:
                eo.entity_position = (float(ep_el.get("x",0)), float(ep_el.get("y",0)), float(ep_el.get("z",0)))
            eo.may_not_exist = bval(item, "EntityMayNotAlwaysExist", True)
            eo.prevent_art   = bval(item, "SpecificallyPreventArtPoints", False)
    cg = root.find("ChainingGraph")
    if cg is not None:
        nodes_el = cg.find("Nodes")
        if nodes_el is not None:
            for item in nodes_el.findall("Item"):
                cn = props.chaining_nodes.add()
                pos = item.find("Position")
                if pos is not None: cn.position = (float(pos.get("x",0)), float(pos.get("y",0)), float(pos.get("z",0)))
                st = item.find("ScenarioType")
                cn.scenario_type = (st.text or "standing").strip() if st is not None else "standing"
                hi = item.find("HasIncomingEdges")
                cn.has_incoming = (hi.get("value","false").lower() == "true") if hi is not None else False
                ho = item.find("HasOutgoingEdges")
                cn.has_outgoing = (ho.get("value","true").lower() == "true") if ho is not None else True
        edges_el = cg.find("Edges")
        if edges_el is not None:
            for item in edges_el.findall("Item"):
                ce = props.chaining_edges.add()
                ce.node_from = ival(item, "NodeIndexFrom", 0); ce.node_to = ival(item, "NodeIndexTo", 0)
                ce.action    = ival(item, "Action", 0); ce.nav_mode = ival(item, "NavMode", 1)
                ce.nav_speed = ival(item, "NavSpeed", 2)
        chains_el = cg.find("Chains")
        if chains_el is not None:
            for item in chains_el.findall("Item"):
                ch = props.chains.add()
                hk = item.find("hash_44F1B77A")
                ch.hash_name = hk.get("value","") if hk is not None else ""
                ei = item.find("EdgeIds")
                ch.edge_ids  = (ei.text or "").strip() if ei is not None else ""
    ag = root.find("AccelGrid")
    if ag is not None:
        props.accel_min_cell_x = ival(ag, "MinCellX", -4); props.accel_max_cell_x = ival(ag, "MaxCellX", 5)
        props.accel_min_cell_y = ival(ag, "MinCellY", -64); props.accel_max_cell_y = ival(ag, "MaxCellY", -48)
        props.accel_cell_dim_x = ival(ag, "CellDimX", 32);  props.accel_cell_dim_y = ival(ag, "CellDimY", 32)
    lu = root.find("LookUps")
    if lu is not None:
        def _collect(tag):
            sec = lu.find(tag)
            return "\n".join((i.text or "").strip() for i in sec.findall("Item")) if sec is not None else ""
        props.type_names         = _collect("TypeNames")
        props.ped_modelset_names = _collect("PedModelSetNames")
        props.veh_modelset_names = _collect("VehicleModelSetNames")
    props.stat_points = len(props.scenario_points)
    props.stat_nodes  = len(props.chaining_nodes)
    props.stat_edges  = len(props.chaining_edges)
    props.stat_chains = len(props.chains)
    return True, "OK"


def _build_ymt_objects(props, col):
    root_obj = bpy.data.objects.new("YMT_Root", None)
    root_obj.empty_display_type = "PLAIN_AXES"; root_obj.empty_display_size = 1.0
    root_obj["ymt_type"] = "root"; _link_obj(root_obj, col)
    sp_root = bpy.data.objects.new("YMT_ScenarioPoints", None)
    sp_root.empty_display_type = "PLAIN_AXES"; sp_root.empty_display_size = 0.1
    sp_root.parent = root_obj; _link_obj(sp_root, col)
    for i, sp in enumerate(props.scenario_points):
        name = ITYPE_NAMES.get(sp.itype, f"type{sp.itype}")
        obj = bpy.data.objects.new(f"YMT_SP_{i}_{name}", None)
        obj.empty_display_type = "SINGLE_ARROW"; obj.empty_display_size = 1.0
        obj.location = (sp.position[0], sp.position[1], sp.position[2])
        obj.rotation_euler = (0, 0, sp.position[3])
        obj["ymt_type"] = "scenario_point"; obj["sp_index"] = i
        obj["itype"] = sp.itype; obj["flags"] = sp.flags
        obj["time_start"] = sp.time_start; obj["time_end"] = sp.time_end
        obj["model_set_id"] = sp.model_set_id; obj["probability"] = sp.probability
        obj.parent = sp_root; _link_obj(obj, col)
    cn_root = bpy.data.objects.new("YMT_ChainingNodes", None)
    cn_root.empty_display_type = "PLAIN_AXES"; cn_root.empty_display_size = 0.1
    cn_root.parent = root_obj; _link_obj(cn_root, col)
    for i, cn in enumerate(props.chaining_nodes):
        obj = bpy.data.objects.new(f"YMT_CNode_{i}_{cn.scenario_type}", None)
        obj.empty_display_type = "CIRCLE"; obj.empty_display_size = 0.5
        obj.location = cn.position
        obj["ymt_type"] = "chaining_node"; obj["cn_index"] = i
        obj["scenario_type"] = cn.scenario_type
        obj.parent = cn_root; _link_obj(obj, col)
    return root_obj


def _build_ymt_xml(context, props):
    for obj in context.scene.objects:
        if obj.get("ymt_type") == "scenario_point":
            idx = obj.get("sp_index", -1)
            if 0 <= idx < len(props.scenario_points):
                sp = props.scenario_points[idx]
                sp.position = (obj.location.x, obj.location.y, obj.location.z, obj.rotation_euler.z)
                sp.itype = obj.get("itype", sp.itype)
                sp.flags = obj.get("flags", sp.flags)
                sp.time_start = obj.get("time_start", sp.time_start)
                sp.time_end   = obj.get("time_end",   sp.time_end)
        elif obj.get("ymt_type") == "chaining_node":
            idx = obj.get("cn_index", -1)
            if 0 <= idx < len(props.chaining_nodes):
                props.chaining_nodes[idx].position = tuple(obj.location)
    root = ET.Element("CScenarioPointRegion")
    sub_val(root, "VersionNumber", props.version_number)
    points_el = ET.SubElement(root, "Points")
    ET.SubElement(points_el, "LoadSavePoints", itemType="CExtensionDefSpawnPoint")
    my_pts = ET.SubElement(points_el, "MyPoints", itemType="CScenarioPoint")
    for sp in props.scenario_points:
        item = ET.SubElement(my_pts, "Item")
        sub_val(item, "iType", sp.itype); sub_val(item, "ModelSetId", sp.model_set_id)
        sub_val(item, "iInterior", sp.interior_id); sub_val(item, "iRequiredIMapId", sp.imap_id)
        sub_val(item, "iProbability", sp.probability); sub_val(item, "uAvailableInMpSp", sp.avail_mp_sp)
        sub_val(item, "iTimeStartOverride", sp.time_start); sub_val(item, "iTimeEndOverride", sp.time_end)
        sub_val(item, "iRadius", sp.radius); sub_val(item, "iTimeTillPedLeaves", sp.time_till_leaves)
        sub_val(item, "iScenarioGroup", sp.scenario_group)
        ET.SubElement(item, "Flags").text = sp.flags
        pos_el = ET.SubElement(item, "vPositionAndDirection")
        pos_el.set("x", f"{sp.position[0]:.7g}"); pos_el.set("y", f"{sp.position[1]:.7g}")
        pos_el.set("z", f"{sp.position[2]:.7g}"); pos_el.set("w", f"{sp.position[3]:.7g}")
    eo_el = ET.SubElement(root, "EntityOverrides", itemType="CScenarioEntityOverride")
    for eo in props.entity_overrides:
        item = ET.SubElement(eo_el, "Item")
        ep = ET.SubElement(item, "EntityPosition")
        ep.set("x", f"{eo.entity_position[0]:.7g}"); ep.set("y", f"{eo.entity_position[1]:.7g}"); ep.set("z", f"{eo.entity_position[2]:.7g}")
        sub_text(item, "EntityType", eo.entity_type)
        ET.SubElement(item, "ScenarioPoints", itemType="CExtensionDefSpawnPoint")
        sub_val(item, "EntityMayNotAlwaysExist", str(eo.may_not_exist).lower())
        sub_val(item, "SpecificallyPreventArtPoints", str(eo.prevent_art).lower())
    cg_el = ET.SubElement(root, "ChainingGraph")
    nodes_el = ET.SubElement(cg_el, "Nodes", itemType="CScenarioChainingNode")
    for cn in props.chaining_nodes:
        item = ET.SubElement(nodes_el, "Item")
        pos_el = ET.SubElement(item, "Position")
        pos_el.set("x", f"{cn.position[0]:.7g}"); pos_el.set("y", f"{cn.position[1]:.7g}"); pos_el.set("z", f"{cn.position[2]:.7g}")
        ET.SubElement(item, "hash_9B1D60AB")
        sub_text(item, "ScenarioType", cn.scenario_type)
        sub_val(item, "HasIncomingEdges", str(cn.has_incoming).lower())
        sub_val(item, "HasOutgoingEdges", str(cn.has_outgoing).lower())
    edges_el = ET.SubElement(cg_el, "Edges", itemType="CScenarioChainingEdge")
    for ce in props.chaining_edges:
        item = ET.SubElement(edges_el, "Item")
        sub_val(item, "NodeIndexFrom", ce.node_from); sub_val(item, "NodeIndexTo", ce.node_to)
        sub_val(item, "Action", ce.action); sub_val(item, "NavMode", ce.nav_mode); sub_val(item, "NavSpeed", ce.nav_speed)
    chains_el = ET.SubElement(cg_el, "Chains", itemType="CScenarioChain")
    for ch in props.chains:
        item = ET.SubElement(chains_el, "Item")
        sub_val(item, "hash_44F1B77A", ch.hash_name)
        ET.SubElement(item, "EdgeIds").text = ch.edge_ids
    ag_el = ET.SubElement(root, "AccelGrid")
    sub_val(ag_el, "MinCellX", props.accel_min_cell_x); sub_val(ag_el, "MaxCellX", props.accel_max_cell_x)
    sub_val(ag_el, "MinCellY", props.accel_min_cell_y); sub_val(ag_el, "MaxCellY", props.accel_max_cell_y)
    sub_val(ag_el, "CellDimX", props.accel_cell_dim_x); sub_val(ag_el, "CellDimY", props.accel_cell_dim_y)
    ET.SubElement(root, "hash_E529D603")
    ET.SubElement(root, "Clusters", itemType="CScenarioPointCluster")
    lu_el = ET.SubElement(root, "LookUps")
    def _write_names(tag, names_str):
        sec = ET.SubElement(lu_el, tag)
        for name in names_str.split("\n"):
            name = name.strip()
            if name: sub_text(sec, "Item", name)
    _write_names("TypeNames", props.type_names)
    _write_names("PedModelSetNames", props.ped_modelset_names)
    _write_names("VehicleModelSetNames", props.veh_modelset_names)
    ET.SubElement(lu_el, "GroupNames"); ET.SubElement(lu_el, "InteriorNames"); ET.SubElement(lu_el, "RequiredIMapNames")
    return to_xml_string(root)


# ── OPERATEURS ──────────────────────────────────────────────────────────────

class YMT_OT_Import(Operator):
    """Importe un fichier Scenario YMT XML"""
    bl_idname = "gta5_ymt.import_xml"; bl_label = "Importer YMT XML"
    bl_options = {"REGISTER", "UNDO"}
    filepath:   StringProperty(subtype="FILE_PATH")
    filter_glob:StringProperty(default="*.xml;*.ymt;*.ymt.xml", options={"HIDDEN"})
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self); return {"RUNNING_MODAL"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ymt
        ok, msg = _parse_ymt_xml(self.filepath, props)
        if not ok: self.report({"ERROR"}, msg); return {"CANCELLED"}
        props.filepath = self.filepath
        col = _get_or_create_col(YMT_COLLECTION)
        for obj in list(col.objects): bpy.data.objects.remove(obj, do_unlink=True)
        _build_ymt_objects(props, col)
        self.report({"INFO"}, f"YMT importé : {props.stat_points} points, {props.stat_nodes} noeuds, {props.stat_edges} arêtes")
        return {"FINISHED"}


class YMT_OT_Export(Operator):
    """Exporte les scénarios en fichier .ymt XML (compatible OpenIV/CodeWalker)"""
    bl_idname = "gta5_ymt.export_xml"; bl_label = "Exporter .ymt XML"
    bl_options = {"REGISTER"}
    filepath:   StringProperty(subtype="FILE_PATH")
    filter_glob:StringProperty(default="*.ymt;*.ymt.xml;*.xml", options={"HIDDEN"})
    def invoke(self, context, event):
        props = context.scene.gta5_pathing.ymt
        # Conserver le même nom de fichier avec extension .ymt.xml
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
        self.report({"INFO"}, f"YMT exporté → {self.filepath}")
        return {"FINISHED"}


class YMT_OT_AddScenarioPoint(Operator):
    """Ajoute un point de scénario au curseur"""
    bl_idname = "gta5_ymt.add_scenario_point"; bl_label = "Ajouter Point Scénario"
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
    """Supprime le point de scénario sélectionné"""
    bl_idname = "gta5_ymt.remove_scenario_point"; bl_label = "Supprimer Point"
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
    """Ajoute un noeud de chaînage au curseur"""
    bl_idname = "gta5_ymt.add_chaining_node"; bl_label = "Ajouter Noeud Chaînage"
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
    """Ajoute une arête entre deux noeuds de chaînage"""
    bl_idname = "gta5_ymt.add_chaining_edge"; bl_label = "Ajouter Arête"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ymt
        ce = props.chaining_edges.add(); ce.node_from = 0; ce.node_to = 0; ce.nav_mode = 1; ce.nav_speed = 2
        props.chain_edge_index = len(props.chaining_edges) - 1
        props.stat_edges = len(props.chaining_edges)
        return {"FINISHED"}


class YMT_OT_RemoveChainingEdge(Operator):
    """Supprime l'arête de chaînage sélectionnée"""
    bl_idname = "gta5_ymt.remove_chaining_edge"; bl_label = "Supprimer Arête"
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
    """Supprime toutes les arêtes du noeud sélectionné"""
    bl_idname = "gta5_ymt.remove_all_edges_node"; bl_label = "Supprimer Arêtes du Noeud"
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
        self.report({"INFO"}, f"{len(to_remove)} arête(s) supprimée(s)")
        return {"FINISHED"}


class YMT_OT_SyncFromObjects(Operator):
    """Synchronise depuis les empties Blender"""
    bl_idname = "gta5_ymt.sync_from_objects"; bl_label = "Sync depuis Objets"
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
        self.report({"INFO"}, f"Sync : {cnt} objets mis à jour")
        return {"FINISHED"}


_classes = [
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
