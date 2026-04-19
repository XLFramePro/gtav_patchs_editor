"""
operators_ynd.py — PathNodes YND complet avec flags structurés (référence ynd.rar).
Import/Export XML + gestion complète noeuds/liens + détection automatique ped/véhicule.
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

def _int_to_special_type(v):
    spec_raw = v >> 3
    m = {0:"NONE",2:"PARKING",10:"PED_CROSSING",14:"PED_ASSISTED",
         15:"TRAFFIC_LIGHT",16:"STOP_SIGN",17:"CAUTION",18:"PED_NOWAIT",
         19:"EMERGENCY",20:"OFFROAD_JCT"}
    return m.get(spec_raw, "NONE")

def _int_to_speed(v):
    m = {0:"SLOW",2:"NORMAL",4:"FAST",6:"FASTER"}
    return m.get(v & 0xFE, "NORMAL")

def _apply_node_flags(n, f0, f1, f2, f3, f4, f5):
    """Applique les 6 raw ints dans les PropertyGroups flags structurés."""
    nf0 = n.flags0
    nf0.scripted        = bool(f0 & 1);   nf0.gps_enabled    = bool(f0 & 2)
    nf0.unused_4        = bool(f0 & 4);   nf0.offroad        = bool(f0 & 8)
    nf0.unused_16       = bool(f0 & 16);  nf0.no_big_vehicles= bool(f0 & 32)
    nf0.cannot_go_right = bool(f0 & 64);  nf0.cannot_go_left = bool(f0 & 128)

    nf1 = n.flags1
    nf1.slip_lane           = bool(f1 & 1)
    nf1.indicate_keep_left  = bool(f1 & 2)
    nf1.indicate_keep_right = bool(f1 & 4)
    nf1.special_type        = _int_to_special_type(f1)

    nf2 = n.flags2
    nf2.no_gps      = bool(f2 & 1);   nf2.unused_2   = bool(f2 & 2)
    nf2.junction    = bool(f2 & 4);   nf2.unused_8   = bool(f2 & 8)
    nf2.disabled_1  = bool(f2 & 16);  nf2.water_boats= bool(f2 & 32)
    nf2.freeway     = bool(f2 & 64);  nf2.disabled_2 = bool(f2 & 128)

    nf3 = n.flags3
    nf3.tunnel    = bool(f3 & 1)
    nf3.heuristic = (f3 >> 1) & 127

    nf4 = n.flags4
    nf4.density       = f4 & 0xF
    nf4.deadendness   = (f4 >> 4) & 7
    nf4.left_turn_only= bool(f4 & 128)

    nf5 = n.flags5
    nf5.has_junction_heightmap = bool(f5 & 1)
    nf5.speed = _int_to_speed(f5)

    # Stocker raw pour export rapide
    n.raw0=f0; n.raw1=f1; n.raw2=f2; n.raw3=f3; n.raw4=f4; n.raw5=f5


def _node_flags_to_ints(n):
    """Reconvertit les PropertyGroups en 6 ints pour l'export XML."""
    f0 = n.flags0.to_int()
    f1 = n.flags1.to_int()
    f2 = n.flags2.to_int()
    f3 = n.flags3.to_int()
    f4 = n.flags4.to_int()
    f5 = n.flags5.to_int()
    return f0, f1, f2, f3, f4, f5


def _apply_link_flags(lk, f0, f1, f2):
    lf0 = lk.flags0
    lf0.gps_both_ways     = bool(f0 & 1)
    lf0.block_if_no_lanes = bool(f0 & 2)
    lf0.unknown_1         = (f0 >> 2) & 7
    lf0.unknown_2         = (f0 >> 5) & 7

    lf1 = lk.flags1
    lf1.unused_1        = bool(f1 & 1)
    lf1.narrow_road     = bool(f1 & 2)
    lf1.dead_end        = bool(f1 & 4)
    lf1.dead_end_exit   = bool(f1 & 8)
    lf1.offset          = (f1 >> 4) & 7
    lf1.negative_offset = bool(f1 & 128)

    lf2 = lk.flags2
    lf2.dont_use_for_navigation = bool(f2 & 1)
    lf2.shortcut                = bool(f2 & 2)
    lf2.back_lanes              = (f2 >> 2) & 7
    lf2.forward_lanes           = (f2 >> 5) & 7

    lk.raw_flags0 = f0; lk.raw_flags1 = f1; lk.raw_flags2 = f2


def _link_flags_to_ints(lk):
    return lk.flags0.to_int(), lk.flags1.to_int(), lk.flags2.to_int()


def _node_is_vehicle(n):
    return n.flags1.special_type not in PED_SPECIAL_TYPES


def _node_is_freeway(n):
    return n.flags2.freeway

def _node_is_junction(n):
    return n.flags2.junction


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
        return False, f"Racine attendue NodeDictionary, trouvée {root.tag}"

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
        # Cubes pour véhicules, sphères pour piétons (comme dans la référence)
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
    return root_obj


# ─────────────────────────────────────────────────────────────────────────────
#  EXPORT XML
# ─────────────────────────────────────────────────────────────────────────────

def _build_ynd_xml(context, props):
    # Sync positions depuis les empties
    for obj in context.scene.objects:
        if obj.get("ynd_type") == "node":
            idx = obj.get("node_index", -1)
            if 0 <= idx < len(props.nodes):
                props.nodes[idx].position = tuple(obj.location)

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
        pos.set("x", f"{node.position[0]:.5g}")
        pos.set("y", f"{node.position[1]:.5g}")
        pos.set("z", f"{node.position[2]:.5g}")
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
    """Importe un fichier PathNodes YND XML"""
    bl_idname = "gta5_ynd.import_xml"; bl_label = "Importer YND XML"
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
            f"YND importé : {props.stat_vehicle} véhicules, "
            f"{props.stat_ped} piétons, {props.stat_junctions} carrefours")
        return {"FINISHED"}


class YND_OT_Export(Operator):
    """Exporte les PathNodes en YND XML"""
    bl_idname = "gta5_ynd.export_xml"; bl_label = "Exporter YND XML"
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
        self.report({"INFO"}, f"YND exporté → {self.filepath}")
        return {"FINISHED"}


class YND_OT_AddVehicleNode(Operator):
    """Ajoute un noeud véhicule au curseur 3D"""
    bl_idname = "gta5_ynd.add_vehicle_node"; bl_label = "Ajouter Noeud Véhicule"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        n = props.nodes.add()
        n.node_id    = len(props.nodes) - 1
        n.area_id    = props.area_id
        cursor       = context.scene.cursor.location
        n.position   = (cursor.x, cursor.y, cursor.z)
        # Flags par défaut véhicule : Normal speed, GPS enabled
        _apply_node_flags(n, 2, 0, 0, 64, 134, 2)
        props.node_index   = len(props.nodes) - 1
        props.stat_nodes   = len(props.nodes)
        props.stat_vehicle = sum(1 for nd in props.nodes if _node_is_vehicle(nd))
        props.stat_ped     = sum(1 for nd in props.nodes if not _node_is_vehicle(nd))
        col = _get_or_create_col(YND_COLLECTION)
        obj = bpy.data.objects.new(f"YND_V_{n.area_id}_{n.node_id}", None)
        obj.empty_display_type = "CUBE"; obj.empty_display_size = 0.5
        obj.location = n.position; obj.lock_rotation = (True,True,True); obj.lock_scale = (True,True,True)
        obj["ynd_type"]="node"; obj["node_index"]=props.node_index
        obj["node_area_id"]=n.area_id; obj["node_id"]=n.node_id
        obj["is_vehicle"]=True; obj["is_freeway"]=False; obj["is_junction"]=False
        _link_obj(obj, col)
        self.report({"INFO"}, f"Noeud véhicule ajouté : {n.area_id}:{n.node_id}")
        return {"FINISHED"}


class YND_OT_AddPedNode(Operator):
    """Ajoute un noeud piéton au curseur 3D"""
    bl_idname = "gta5_ynd.add_ped_node"; bl_label = "Ajouter Noeud Piéton"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        n = props.nodes.add()
        n.node_id  = len(props.nodes) - 1
        n.area_id  = props.area_id
        cursor     = context.scene.cursor.location
        n.position = (cursor.x, cursor.y, cursor.z)
        # flags1 avec special_type PED_CROSSING (valeur 10 << 3 = 80)
        _apply_node_flags(n, 2, 80, 0, 8, 2, 2)
        props.node_index   = len(props.nodes) - 1
        props.stat_nodes   = len(props.nodes)
        props.stat_vehicle = sum(1 for nd in props.nodes if _node_is_vehicle(nd))
        props.stat_ped     = sum(1 for nd in props.nodes if not _node_is_vehicle(nd))
        col = _get_or_create_col(YND_COLLECTION)
        obj = bpy.data.objects.new(f"YND_P_{n.area_id}_{n.node_id}", None)
        obj.empty_display_type = "SPHERE"; obj.empty_display_size = 0.3
        obj.location = n.position; obj.lock_rotation = (True,True,True); obj.lock_scale = (True,True,True)
        obj["ynd_type"]="node"; obj["node_index"]=props.node_index
        obj["node_area_id"]=n.area_id; obj["node_id"]=n.node_id
        obj["is_vehicle"]=False; obj["is_freeway"]=False; obj["is_junction"]=False
        _link_obj(obj, col)
        self.report({"INFO"}, f"Noeud piéton ajouté : {n.area_id}:{n.node_id}")
        return {"FINISHED"}


class YND_OT_RemoveNode(Operator):
    """Supprime le noeud actif + tous ses liens entrants dans les autres noeuds"""
    bl_idname = "gta5_ynd.remove_node"; bl_label = "Supprimer Noeud"
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
        # Supprimer les liens entrants dans tous les autres noeuds
        for n in props.nodes:
            idxs = [i for i, lk in enumerate(n.links)
                    if lk.to_area_id == r_area and lk.to_node_id == r_id]
            for i in reversed(idxs): n.links.remove(i)
        props.nodes.remove(idx)
        props.node_index   = min(idx, len(props.nodes) - 1)
        props.stat_nodes   = len(props.nodes)
        props.stat_vehicle = sum(1 for n in props.nodes if _node_is_vehicle(n))
        props.stat_ped     = sum(1 for n in props.nodes if not _node_is_vehicle(n))
        props.stat_junctions = sum(1 for n in props.nodes if _node_is_junction(n))
        return {"FINISHED"}


class YND_OT_AddLink(Operator):
    """Ajoute un lien sortant au noeud actif"""
    bl_idname = "gta5_ynd.add_link"; bl_label = "Ajouter Lien"
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
        return {"FINISHED"}


class YND_OT_RemoveLink(Operator):
    """Supprime le lien actif du noeud"""
    bl_idname = "gta5_ynd.remove_link"; bl_label = "Supprimer Lien"
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
        return {"FINISHED"}


class YND_OT_RemoveAllLinks(Operator):
    """Supprime TOUS les liens du noeud actif"""
    bl_idname = "gta5_ynd.remove_all_links"; bl_label = "Supprimer Tous les Liens"
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
        self.report({"INFO"}, f"{count} lien(s) supprimé(s)")
        return {"FINISHED"}


class YND_OT_LinkTwoNodes(Operator):
    """Crée un lien du noeud actif vers un noeud cible"""
    bl_idname = "gta5_ynd.link_two_nodes"; bl_label = "Lier vers Noeud Cible"
    bl_options = {"REGISTER", "UNDO"}
    target_node_id: IntProperty(name="Node ID cible", default=0, min=0)
    target_area_id: IntProperty(name="Area ID cible", default=400, min=0)
    bidirectional:  BoolProperty(name="Bidirectionnel", default=True)
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
        self.report({"INFO"}, f"Lien {'↔' if self.bidirectional else '→'} créé, L={dist}")
        return {"FINISHED"}


class YND_OT_SyncFromObjects(Operator):
    """Synchronise les positions depuis les empties Blender"""
    bl_idname = "gta5_ynd.sync_from_objects"; bl_label = "Sync depuis Objets"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        count = 0
        for obj in context.scene.objects:
            if obj.get("ynd_type") == "node":
                idx = obj.get("node_index", -1)
                if 0 <= idx < len(props.nodes):
                    props.nodes[idx].position = tuple(obj.location); count += 1
        self.report({"INFO"}, f"{count} noeuds synchronisés")
        return {"FINISHED"}


_classes = [
    YND_OT_Import, YND_OT_Export,
    YND_OT_AddVehicleNode, YND_OT_AddPedNode, YND_OT_RemoveNode,
    YND_OT_AddLink, YND_OT_RemoveLink, YND_OT_RemoveAllLinks,
    YND_OT_LinkTwoNodes, YND_OT_SyncFromObjects,
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
