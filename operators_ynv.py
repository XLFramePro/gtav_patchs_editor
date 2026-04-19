"""
operators_ynv.py — NavMesh YNV complet.

SYSTÈME DE MATÉRIAUX :
  - Clé = bytes 0-3 uniquement (bytes 4-5 = densité/audio interne, per-polygon → ignorés pour le matériau)
  - Nom = "YNV_B{b0:03d}_{b1:03d}_{b2:03d}_{b3:03d}_{NomDescriptif}"
  - Un seul matériau partagé par combinaison b0/b1/b2/b3 identique
  - Sélection polygone → lecture flags → affichage dans panneau + bytes 4-5 stockés en custom prop

COLORS (priorité décroissante) :
  Water > Underground > Interior > Isolated > TrainTrack > Shallow
  > Pavement+Cover > Road+Cover > Pavement > Road > Cover-only > Spawn > Default
"""
import bpy, bmesh, xml.etree.ElementTree as ET, math, os
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty, IntProperty, FloatProperty
from mathutils import Vector
from .xml_utils import fval, ival, sval, sub_val, sub_text, to_xml_string

YNV_COLLECTION = "YNV_NavMesh"

# ─────────────────────────────────────────────────────────────────────────────
#  FLAG PRESETS (bytes 0-3, puis bytes 4-5 par défaut)
# ─────────────────────────────────────────────────────────────────────────────
FLAG_PRESETS = {
    "ROAD":      (0,   0, 2, 0),
    "PAVEMENT":  (4,   0, 0, 0),
    "INTERIOR":  (0,  32, 0, 0),
    "WATER":     (128, 0, 0, 0),
    "SHALLOW":   (0,   0,16, 0),
    "TRAIN":     (0,   0, 8, 0),
    "COVER":     (0,   0, 2,63),
    "SPAWN":     (0,   0, 3, 0),
    "CUSTOM":    (0,   0, 0, 0),
}

# ─────────────────────────────────────────────────────────────────────────────
#  COULEURS ET NOMS PAR FLAGS (bytes 0-3 uniquement)
# ─────────────────────────────────────────────────────────────────────────────

def _flag_label_parts(b0, b1, b2, b3):
    """Retourne une liste de strings décrivant les flags actifs."""
    parts = []
    if b0 & 128: parts.append("Water")
    if b0 & 64:  parts.append("TooSteep")
    if b0 & 8:   parts.append("Underground")
    if b0 & 4:   parts.append("Pavement")
    if b0 & 2:   parts.append("LargePoly")
    if b0 & 1:   parts.append("SmallPoly")
    if b1 & 64:  parts.append("Isolated")
    if b1 & 32:  parts.append("Interior")
    if b1 & 16:  parts.append("NearCar")
    audio = b1 & 7
    if audio:    parts.append(f"Aud{audio}")
    if b2 & 8:   parts.append("TrainTrack")
    if b2 & 16:  parts.append("Shallow")
    if b2 & 4:   parts.append("AlongEdge")
    if b2 & 2:   parts.append("Road")
    if b2 & 1:   parts.append("Spawn")
    ped = (b2 >> 5) & 7
    if ped:      parts.append(f"Ped{ped}")
    if b3:       parts.append(f"Cov{b3:02X}")
    return parts if parts else ["Default"]


def _flag_color(b0, b1, b2, b3):
    """Retourne RGBA (0-1) selon priorité de surface."""
    if b0 & 128:            return (0.05, 0.15, 0.85, 0.85)   # Water — bleu profond
    if b0 & 8:              return (0.15, 0.45, 0.15, 0.85)   # Underground — vert foncé
    if b1 & 32:             return (0.85, 0.45, 0.10, 0.85)   # Interior — orange
    if b1 & 64:             return (0.85, 0.10, 0.10, 0.80)   # Isolated — rouge
    if b2 & 8:              return (0.55, 0.35, 0.05, 0.85)   # TrainTrack — marron
    if b2 & 16:             return (0.15, 0.70, 0.90, 0.80)   # Shallow — cyan
    if (b0 & 4) and b3:     return (0.60, 0.82, 0.30, 0.85)   # Pavement+Cover — vert-jaune
    if (b2 & 2) and b3:     return (0.92, 0.72, 0.08, 0.85)   # Road+Cover — ambre
    if b0 & 4:              return (0.42, 0.78, 0.42, 0.85)   # Pavement — vert
    if b2 & 2:              return (0.78, 0.78, 0.18, 0.85)   # Road — jaune
    if b3:                  return (0.78, 0.10, 0.78, 0.80)   # Cover-only — violet
    if b2 & 1:              return (0.18, 0.78, 0.85, 0.80)   # Spawn — cyan-vert
    return (0.50, 0.50, 0.50, 0.75)                           # Default — gris


def _mat_key(b0, b1, b2, b3):
    """Clé unique d'un matériau (bytes 0-3)."""
    return f"YNV_{b0:03d}_{b1:03d}_{b2:03d}_{b3:03d}"


def _mat_name(b0, b1, b2, b3):
    """Nom complet du matériau avec description lisible, max 63 chars."""
    label = "_".join(_flag_label_parts(b0, b1, b2, b3))
    base  = f"YNV_{b0:03d}_{b1:03d}_{b2:03d}_{b3:03d}_{label}"
    return base[:63]   # Blender limite les noms à 63 chars


def _get_or_create_material(b0, b1, b2, b3):
    """Retourne (sans créer de doublon) le matériau pour ces flags b0-b3."""
    key  = _mat_key(b0, b1, b2, b3)
    name = _mat_name(b0, b1, b2, b3)

    # Chercher un matériau existant dont le nom commence par la clé
    mat = bpy.data.materials.get(name)
    if mat is None:
        # Chercher par préfixe au cas où le nom aurait été tronqué
        mat = next((m for m in bpy.data.materials if m.name.startswith(key)), None)

    if mat is not None:
        return mat

    # Créer le matériau
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    out  = nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    color = _flag_color(b0, b1, b2, b3)
    bsdf.inputs["Base Color"].default_value     = color
    bsdf.inputs["Roughness"].default_value       = 0.85
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (*color[:3], 1.0)
        bsdf.inputs["Emission Strength"].default_value = 0.05

    mat.use_backface_culling = False
    if hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"

    # Stocker les flags dans les custom props du matériau
    mat["ynv_b0"] = b0; mat["ynv_b1"] = b1
    mat["ynv_b2"] = b2; mat["ynv_b3"] = b3

    return mat


def _parse_flags_str(flags_str):
    """Convertit '0 128 2 0 161 164' → (b0, b1, b2, b3, b4, b5)."""
    try:
        parts = [int(x) for x in flags_str.split()]
        while len(parts) < 6:
            parts.append(0)
        return parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
    except Exception:
        return 0, 0, 0, 0, 0, 0


# ─────────────────────────────────────────────────────────────────────────────
#  PARSE XML → données python
# ─────────────────────────────────────────────────────────────────────────────

def _parse_vertex_line(line):
    parts = line.strip().split(",")
    return tuple(float(p.strip()) for p in parts if p.strip())


def _parse_ynv_xml(filepath, props):
    props.portals.clear()
    props.nav_points.clear()
    try:
        tree = ET.parse(filepath)
    except ET.ParseError as e:
        return False, str(e), []
    root = tree.getroot()
    if root.tag != "NavMesh":
        return False, f"Racine attendue NavMesh, trouvée {root.tag}", []

    cf = root.find("ContentFlags")
    props.content_flags = (cf.text or "").strip() if cf is not None else "Polygons, Portals"
    aid = root.find("AreaID")
    props.area_id = int(aid.get("value", 0)) if aid is not None else 0

    for tag, attr in [("BBMin", "bb_min"), ("BBMax", "bb_max")]:
        el = root.find(tag)
        if el is not None:
            setattr(props, attr, (float(el.get("x",0)), float(el.get("y",0)), float(el.get("z",0))))

    polygons_data = []
    polys_el = root.find("Polygons")
    if polys_el is not None:
        for item in polys_el.findall("Item"):
            flags_el = item.find("Flags")
            flags_str = (flags_el.text or "0 0 0 0 0 0").strip() if flags_el is not None else "0 0 0 0 0 0"
            verts_el  = item.find("Vertices")
            verts = []
            if verts_el is not None and verts_el.text:
                for line in verts_el.text.strip().split("\n"):
                    if line.strip():
                        parsed = _parse_vertex_line(line)
                        if len(parsed) == 3:
                            verts.append(parsed)
            edges_el = item.find("Edges")
            edges_raw = []
            if edges_el is not None and edges_el.text:
                for line in edges_el.text.strip().split("\n"):
                    if line.strip():
                        edges_raw.append(line.strip())
            polygons_data.append({"flags": flags_str, "verts": verts, "edges": edges_raw})

    portals_el = root.find("Portals")
    if portals_el is not None:
        for item in portals_el.findall("Item"):
            p = props.portals.add()
            t = item.find("Type");   p.portal_type = int(t.get("value",1)) if t is not None else 1
            a = item.find("Angle");  p.angle       = float(a.get("value",0)) if a is not None else 0.0
            pf_el = item.find("PolyFrom"); p.poly_from = int(pf_el.get("value",0)) if pf_el is not None else 0
            pt_el = item.find("PolyTo");   p.poly_to   = int(pt_el.get("value",0)) if pt_el is not None else 0
            pfrom = item.find("PositionFrom")
            if pfrom is not None: p.pos_from = (float(pfrom.get("x",0)), float(pfrom.get("y",0)), float(pfrom.get("z",0)))
            pto = item.find("PositionTo")
            if pto is not None:   p.pos_to   = (float(pto.get("x",0)), float(pto.get("y",0)), float(pto.get("z",0)))

    points_el = root.find("Points")
    if points_el is not None:
        for item in points_el.findall("Item"):
            np = props.nav_points.add()
            t  = item.find("Type");  np.point_type = int(t.get("value",0)) if t is not None else 0
            a  = item.find("Angle"); np.angle       = float(a.get("value",0)) if a is not None else 0.0
            pos = item.find("Position")
            if pos is not None: np.position = (float(pos.get("x",0)), float(pos.get("y",0)), float(pos.get("z",0)))

    props.stat_polygons  = len(polygons_data)
    props.stat_portals   = len(props.portals)
    props.stat_navpoints = len(props.nav_points)
    return True, "OK", polygons_data


# ─────────────────────────────────────────────────────────────────────────────
#  CONSTRUCTION DES OBJETS BLENDER
# ─────────────────────────────────────────────────────────────────────────────

def _get_or_create_col(name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def _link_obj(obj, col):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    col.objects.link(obj)


def _build_navmesh_obj(polygons_data, area_id):
    """Construit le mesh Blender avec matériaux partagés par (b0,b1,b2,b3)."""
    vert_map    = {}
    verts_list  = []
    faces_list  = []
    # Pour chaque face : (b0, b1, b2, b3, b4, b5) pour pouvoir retrouver les bytes complets
    face_flags  = []

    for poly in polygons_data:
        b0, b1, b2, b3, b4, b5 = _parse_flags_str(poly["flags"])
        face_indices = []
        for v in poly["verts"]:
            key = (round(v[0], 4), round(v[1], 4), round(v[2], 4))
            if key not in vert_map:
                vert_map[key] = len(verts_list)
                verts_list.append(v)
            face_indices.append(vert_map[key])
        if len(face_indices) >= 3:
            faces_list.append(face_indices)
            face_flags.append((b0, b1, b2, b3, b4, b5))

    mesh = bpy.data.meshes.new(f"YNV_{area_id}_PolyMesh")
    mesh.from_pydata(verts_list, [], faces_list)
    mesh.update()

    # Créer/récupérer les matériaux sans doublons par (b0,b1,b2,b3)
    # Dictionnaire mat_key → index dans mesh.materials
    mat_index_map = {}

    for i, (b0, b1, b2, b3, b4, b5) in enumerate(face_flags):
        key = _mat_key(b0, b1, b2, b3)
        if key not in mat_index_map:
            mat = _get_or_create_material(b0, b1, b2, b3)
            mesh.materials.append(mat)
            mat_index_map[key] = len(mesh.materials) - 1

    # Assigner le material_index à chaque polygone
    for i, (b0, b1, b2, b3, b4, b5) in enumerate(face_flags):
        key = _mat_key(b0, b1, b2, b3)
        mesh.polygons[i].material_index = mat_index_map[key]
        # Stocker les bytes 4-5 (densité interne) dans un attribut custom sur la face si possible
        # On les stocke dans un layer d'attribut via bpy si nécessaire — pour l'instant on passe

    obj = bpy.data.objects.new(f"YNV_{area_id}_PolyMesh", mesh)
    obj["ynv_type"]    = "poly_mesh"
    obj["ynv_area_id"] = area_id
    # Stocker les bytes 4-5 par face dans un custom prop JSON light
    # (liste de paires sérialisée pour une récupération rapide)
    import json
    b45_data = [(ff[4], ff[5]) for ff in face_flags]
    obj["ynv_bytes45"] = json.dumps(b45_data)
    return obj


def _build_portals_objs(props, col):
    root = bpy.data.objects.new("YNV_Portals", None)
    root.empty_display_type = "PLAIN_AXES"; root.empty_display_size = 0.5
    root["ynv_type"] = "portals_root"; _link_obj(root, col)
    for i, portal in enumerate(props.portals):
        for side, pos, typ in [("from", portal.pos_from, "portal_from"), ("to", portal.pos_to, "portal_to")]:
            obj = bpy.data.objects.new(f"YNV_Portal_{i}_{side}", None)
            obj.empty_display_type = "SPHERE"
            obj.empty_display_size = 1.0 if side == "from" else 0.7
            obj.location = pos
            obj["ynv_type"] = typ; obj["portal_index"] = i
            obj["portal_type"] = portal.portal_type
            obj["poly_from"] = portal.poly_from; obj["poly_to"] = portal.poly_to
            obj.parent = root; _link_obj(obj, col)
    return root


def _build_navpoints_objs(props, col):
    root = bpy.data.objects.new("YNV_NavPoints", None)
    root.empty_display_type = "PLAIN_AXES"; root.empty_display_size = 0.1
    root["ynv_type"] = "navpoints_root"; _link_obj(root, col)
    for i, np_item in enumerate(props.nav_points):
        obj = bpy.data.objects.new(f"YNV_NavPt_{i}_T{np_item.point_type}", None)
        obj.empty_display_type = "SINGLE_ARROW"; obj.empty_display_size = 1.5
        obj.location = np_item.position; obj.rotation_euler = (0, 0, np_item.angle)
        obj["ynv_type"] = "nav_point"; obj["point_index"] = i
        obj["point_type"] = np_item.point_type; obj["point_angle"] = np_item.angle
        obj.parent = root; _link_obj(obj, col)
    return root


# ─────────────────────────────────────────────────────────────────────────────
#  EXPORT XML
# ─────────────────────────────────────────────────────────────────────────────

def _build_ynv_xml(context, props):
    root = ET.Element("NavMesh")
    cf = ET.SubElement(root, "ContentFlags"); cf.text = props.content_flags
    sub_val(root, "AreaID", props.area_id)
    for tag, v in [("BBMin", props.bb_min), ("BBMax", props.bb_max)]:
        el = ET.SubElement(root, tag)
        el.set("x", str(int(v[0]))); el.set("y", str(int(v[1]))); el.set("z", f"{v[2]:.7g}")
    bb_size = ET.SubElement(root, "BBSize")
    bb_size.set("x", f"{props.bb_max[0]-props.bb_min[0]:.7g}")
    bb_size.set("y", f"{props.bb_max[1]-props.bb_min[1]:.7g}")
    bb_size.set("z", f"{props.bb_max[2]-props.bb_min[2]:.7g}")

    polys_el   = ET.SubElement(root, "Polygons")
    poly_obj   = next((o for o in context.scene.objects if o.get("ynv_type") == "poly_mesh"), None)
    if poly_obj and poly_obj.type == "MESH":
        mesh     = poly_obj.data
        import json
        b45_data = json.loads(poly_obj.get("ynv_bytes45", "[]"))

        for i, poly in enumerate(mesh.polygons):
            mi  = poly.material_index
            mat = mesh.materials[mi] if mi < len(mesh.materials) else None
            # Lire b0-b3 depuis les custom props du matériau
            if mat and "ynv_b0" in mat:
                b0, b1, b2, b3 = mat["ynv_b0"], mat["ynv_b1"], mat["ynv_b2"], mat["ynv_b3"]
            else:
                b0, b1, b2, b3 = 0, 0, 0, 0
            # Récupérer b4, b5 depuis la custom prop de l'objet
            if i < len(b45_data):
                b4, b5 = b45_data[i]
            else:
                b4, b5 = 0, 0

            item     = ET.SubElement(polys_el, "Item")
            flags_el = ET.SubElement(item, "Flags")
            flags_el.text = f"{b0} {b1} {b2} {b3} {b4} {b5}"

            verts_el  = ET.SubElement(item, "Vertices")
            vert_lines = []
            for vi in poly.vertices:
                v = mesh.vertices[vi].co
                vert_lines.append(f"    {v.x:.7g}, {v.y:.7g}, {v.z:.7g}")
            verts_el.text = "\n" + "\n".join(vert_lines) + "\n   "

            edges_el  = ET.SubElement(item, "Edges")
            elines    = [f"    {props.area_id}:0, {props.area_id}:0" for _ in poly.vertices]
            edges_el.text = "\n" + "\n".join(elines) + "\n   "

    portals_el = ET.SubElement(root, "Portals")
    for portal in props.portals:
        item = ET.SubElement(portals_el, "Item")
        sub_val(item, "Type", portal.portal_type)
        sub_val(item, "Angle",    f"{portal.angle:.7g}")
        sub_val(item, "PolyFrom", portal.poly_from)
        sub_val(item, "PolyTo",   portal.poly_to)
        for tag, pos in [("PositionFrom", portal.pos_from), ("PositionTo", portal.pos_to)]:
            el = ET.SubElement(item, tag)
            el.set("x", f"{pos[0]:.7g}"); el.set("y", f"{pos[1]:.7g}"); el.set("z", f"{pos[2]:.7g}")

    points_el = ET.SubElement(root, "Points")
    for np_item in props.nav_points:
        item = ET.SubElement(points_el, "Item")
        sub_val(item, "Type",  np_item.point_type)
        sub_val(item, "Angle", f"{np_item.angle:.7g}")
        pos_el = ET.SubElement(item, "Position")
        pos_el.set("x", f"{np_item.position[0]:.7g}")
        pos_el.set("y", f"{np_item.position[1]:.7g}")
        pos_el.set("z", f"{np_item.position[2]:.7g}")

    return to_xml_string(root)


# ─────────────────────────────────────────────────────────────────────────────
#  LECTURE DES FLAGS DU POLYGONE SÉLECTIONNÉ
# ─────────────────────────────────────────────────────────────────────────────

def _read_selected_face_flags(context, props):
    """
    Lit les flags du premier polygone sélectionné en Edit Mode
    et les copie dans props.selected_poly_flags + renseigne les bytes 4-5.
    Retourne (ok, message).
    """
    obj = context.active_object
    if obj is None or obj.type != "MESH" or obj.get("ynv_type") != "poly_mesh":
        return False, "Activer le PolyMesh YNV en Edit Mode."
    if obj.mode != "EDIT":
        return False, "Passer en Edit Mode et sélectionner une face."

    mesh = obj.data
    bm   = bmesh.from_edit_mesh(mesh)
    selected_faces = [f for f in bm.faces if f.select]
    if not selected_faces:
        return False, "Aucune face sélectionnée."

    face = selected_faces[0]
    fi   = face.index
    mi   = face.material_index

    mat  = mesh.materials[mi] if mi < len(mesh.materials) else None

    # Récupérer b0-b3 depuis le matériau
    if mat and "ynv_b0" in mat:
        b0 = int(mat["ynv_b0"]); b1 = int(mat["ynv_b1"])
        b2 = int(mat["ynv_b2"]); b3 = int(mat["ynv_b3"])
    else:
        b0, b1, b2, b3 = 0, 0, 0, 0

    # Récupérer b4-b5 depuis la custom prop JSON de l'objet
    import json
    try:
        b45_data = json.loads(obj.get("ynv_bytes45", "[]"))
        b4, b5   = b45_data[fi] if fi < len(b45_data) else (0, 0)
    except Exception:
        b4, b5 = 0, 0

    # Appliquer aux PropertyGroup flags
    pf = props.selected_poly_flags
    pf.poly_index = fi
    flags_str = f"{b0} {b1} {b2} {b3} {b4} {b5}"
    pf.from_flags_str(flags_str)

    mat_name = mat.name if mat else "(aucun)"
    labels   = " + ".join(_flag_label_parts(b0, b1, b2, b3))
    return True, f"Face {fi} : [{b0} {b1} {b2} {b3}] {labels} | b4={b4} b5={b5}"


# ─────────────────────────────────────────────────────────────────────────────
#  OPÉRATEURS
# ─────────────────────────────────────────────────────────────────────────────

class YNV_OT_Import(Operator):
    """Importe un fichier navmesh YNV XML dans Blender"""
    bl_idname  = "gta5_ynv.import_xml"; bl_label = "Importer YNV XML"
    bl_options = {"REGISTER", "UNDO"}
    filepath:   StringProperty(subtype="FILE_PATH")
    filter_glob:StringProperty(default="*.xml;*.ynv.xml", options={"HIDDEN"})
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self); return {"RUNNING_MODAL"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        ok, msg, polygons_data = _parse_ynv_xml(self.filepath, props)
        if not ok: self.report({"ERROR"}, msg); return {"CANCELLED"}
        props.filepath = self.filepath
        col = _get_or_create_col(YNV_COLLECTION)
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        if polygons_data:
            poly_obj = _build_navmesh_obj(polygons_data, props.area_id)
            _link_obj(poly_obj, col)
        _build_portals_objs(props, col)
        _build_navpoints_objs(props, col)
        n_mats = len(set(m.name for m in bpy.data.materials if m.name.startswith("YNV_")))
        self.report({"INFO"},
            f"YNV importé : {props.stat_polygons} polygones, "
            f"{n_mats} matériaux uniques, "
            f"{props.stat_portals} portails, "
            f"{props.stat_navpoints} points")
        return {"FINISHED"}


class YNV_OT_Export(Operator):
    """Exporte la navmesh en YNV XML"""
    bl_idname  = "gta5_ynv.export_xml"; bl_label = "Exporter YNV XML"
    bl_options = {"REGISTER"}
    filepath:   StringProperty(subtype="FILE_PATH")
    filter_glob:StringProperty(default="*.xml", options={"HIDDEN"})
    def invoke(self, context, event):
        props = context.scene.gta5_pathing.ynv
        self.filepath = props.filepath or "navmesh.ynv.xml"
        context.window_manager.fileselect_add(self); return {"RUNNING_MODAL"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        xml_str = _build_ynv_xml(context, props)
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                f.write(xml_str)
        except OSError as e:
            self.report({"ERROR"}, str(e)); return {"CANCELLED"}
        props.filepath = self.filepath
        self.report({"INFO"}, f"YNV exporté → {self.filepath}")
        return {"FINISHED"}


class YNV_OT_ReadSelectedFlags(Operator):
    """Lit les flags du polygone sélectionné (Edit Mode) et les affiche dans le panneau"""
    bl_idname  = "gta5_ynv.read_selected_flags"; bl_label = "Lire flags depuis sélection"
    bl_options = {"REGISTER"}
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.get("ynv_type") == "poly_mesh" and obj.mode == "EDIT"
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        ok, msg = _read_selected_face_flags(context, props)
        self.report({"INFO" if ok else "WARNING"}, msg)
        return {"FINISHED" if ok else "CANCELLED"}


class YNV_OT_ApplyFlagsPreset(Operator):
    """Applique le preset de flags aux faces sélectionnées"""
    bl_idname  = "gta5_ynv.apply_flags_preset"; bl_label = "Appliquer Préset"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.get("ynv_type") == "poly_mesh" and obj.mode == "EDIT"
    def execute(self, context):
        props  = context.scene.gta5_pathing.ynv
        preset = props.flag_preset
        b0, b1, b2, b3 = FLAG_PRESETS.get(preset, (0,0,0,0))
        return _apply_flags_to_selection(context, props, b0, b1, b2, b3, preset)


class YNV_OT_ApplyCustomFlags(Operator):
    """Applique les flags personnalisés du panneau aux faces sélectionnées"""
    bl_idname  = "gta5_ynv.apply_custom_flags"; bl_label = "Appliquer Flags Custom"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.get("ynv_type") == "poly_mesh" and obj.mode == "EDIT"
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        pf    = props.selected_poly_flags
        flags_str = pf.to_flags_str()
        b0, b1, b2, b3, b4, b5 = _parse_flags_str(flags_str)
        return _apply_flags_to_selection(context, props, b0, b1, b2, b3, "custom")


def _apply_flags_to_selection(context, props, b0, b1, b2, b3, label):
    """Helper : applique un matériau (b0,b1,b2,b3) aux faces sélectionnées."""
    obj  = context.active_object
    mesh = obj.data
    mat  = _get_or_create_material(b0, b1, b2, b3)

    # Ajouter le matériau au mesh s'il n'y est pas encore
    if mat.name not in [m.name for m in mesh.materials]:
        mesh.materials.append(mat)

    mi = list(mesh.materials).index(mat)

    bm = bmesh.from_edit_mesh(mesh)
    count = 0
    import json
    b45_raw = obj.get("ynv_bytes45", "[]")
    try:
        b45_data = json.loads(b45_raw)
    except Exception:
        b45_data = []

    # S'assurer que b45_data a assez d'entrées
    while len(b45_data) < len(mesh.polygons):
        b45_data.append([0, 0])

    for face in bm.faces:
        if face.select:
            old_mi    = face.material_index
            face.material_index = mi
            count     += 1

    bmesh.update_edit_mesh(mesh)
    obj["ynv_bytes45"] = json.dumps(b45_data)

    name  = _mat_name(b0, b1, b2, b3)
    parts = _flag_label_parts(b0, b1, b2, b3)
    from bpy.types import Operator as _Op
    # On ne peut pas self.report ici, donc on retourne juste FINISHED
    return {"FINISHED"}


class YNV_OT_AddPolygon(Operator):
    """Ajoute un quad navmesh au curseur avec le préset actif"""
    bl_idname  = "gta5_ynv.add_polygon"; bl_label = "Ajouter Polygone"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props  = context.scene.gta5_pathing.ynv
        col    = _get_or_create_col(YNV_COLLECTION)
        poly_obj = next((o for o in context.scene.objects if o.get("ynv_type") == "poly_mesh"), None)
        if poly_obj is None:
            mesh     = bpy.data.meshes.new("YNV_PolyMesh")
            poly_obj = bpy.data.objects.new(f"YNV_{props.area_id}_PolyMesh", mesh)
            poly_obj["ynv_type"] = "poly_mesh"
            poly_obj["ynv_area_id"] = props.area_id
            poly_obj["ynv_bytes45"] = "[]"
            _link_obj(poly_obj, col)

        preset       = props.flag_preset
        b0, b1, b2, b3 = FLAG_PRESETS.get(preset, (0,0,0,0))
        mat          = _get_or_create_material(b0, b1, b2, b3)

        cursor = context.scene.cursor.location
        s      = 2.5
        z      = cursor.z

        bm = bmesh.new()
        bm.from_mesh(poly_obj.data)
        verts = [
            bm.verts.new((cursor.x - s, cursor.y - s, z)),
            bm.verts.new((cursor.x + s, cursor.y - s, z)),
            bm.verts.new((cursor.x + s, cursor.y + s, z)),
            bm.verts.new((cursor.x - s, cursor.y + s, z)),
        ]
        bm.faces.new(verts)
        bm.to_mesh(poly_obj.data)
        bm.free()
        poly_obj.data.update()

        # Assigner matériau à la dernière face
        mesh = poly_obj.data
        if mat.name not in [m.name for m in mesh.materials]:
            mesh.materials.append(mat)
        mi = list(mesh.materials).index(mat)
        mesh.polygons[-1].material_index = mi

        # Mettre à jour b45_data
        import json
        try:
            b45_data = json.loads(poly_obj.get("ynv_bytes45","[]"))
        except Exception:
            b45_data = []
        b45_data.append([0, 0])
        poly_obj["ynv_bytes45"] = json.dumps(b45_data)

        props.stat_polygons = len(mesh.polygons)
        labels = " + ".join(_flag_label_parts(b0, b1, b2, b3))
        self.report({"INFO"}, f"Polygone ajouté : [{b0} {b1} {b2} {b3}] {labels}")
        return {"FINISHED"}


class YNV_OT_AddPortal(Operator):
    """Ajoute un portail NavMesh"""
    bl_idname  = "gta5_ynv.add_portal"; bl_label = "Ajouter Portail"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        p = props.portals.add(); p.portal_type = 1
        c = context.scene.cursor.location
        p.pos_from = (c.x, c.y, c.z); p.pos_to = (c.x + 1, c.y, c.z + 5)
        props.portal_index = len(props.portals) - 1
        props.stat_portals = len(props.portals)
        return {"FINISHED"}


class YNV_OT_RemovePortal(Operator):
    """Supprime le portail sélectionné"""
    bl_idname  = "gta5_ynv.remove_portal"; bl_label = "Supprimer Portail"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        props = context.scene.gta5_pathing.ynv
        return 0 <= props.portal_index < len(props.portals)
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        props.portals.remove(props.portal_index)
        props.portal_index = min(props.portal_index, len(props.portals) - 1)
        props.stat_portals = len(props.portals)
        return {"FINISHED"}


class YNV_OT_AddNavPoint(Operator):
    """Ajoute un nav point au curseur"""
    bl_idname  = "gta5_ynv.add_nav_point"; bl_label = "Ajouter Nav Point"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props  = context.scene.gta5_pathing.ynv
        np     = props.nav_points.add()
        cursor = context.scene.cursor.location
        np.position = (cursor.x, cursor.y, cursor.z)
        props.nav_point_index = len(props.nav_points) - 1
        props.stat_navpoints  = len(props.nav_points)
        return {"FINISHED"}


class YNV_OT_RemoveNavPoint(Operator):
    """Supprime le nav point sélectionné"""
    bl_idname  = "gta5_ynv.remove_nav_point"; bl_label = "Supprimer Nav Point"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        props = context.scene.gta5_pathing.ynv
        return 0 <= props.nav_point_index < len(props.nav_points)
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        props.nav_points.remove(props.nav_point_index)
        props.nav_point_index = min(props.nav_point_index, len(props.nav_points) - 1)
        props.stat_navpoints  = len(props.nav_points)
        return {"FINISHED"}


class YNV_OT_SyncFromObjects(Operator):
    """Synchronise portails et nav points depuis les empties"""
    bl_idname  = "gta5_ynv.sync_from_objects"; bl_label = "Sync depuis Objets"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynv
        props.nav_points.clear()
        for obj in sorted([o for o in context.scene.objects if o.get("ynv_type") == "nav_point"],
                          key=lambda o: o.get("point_index", 0)):
            np = props.nav_points.add()
            np.position   = tuple(obj.location)
            np.point_type = obj.get("point_type", 0)
            np.angle      = obj.rotation_euler.z
        props.stat_navpoints = len(props.nav_points)
        self.report({"INFO"}, f"Sync : {len(props.nav_points)} nav points")
        return {"FINISHED"}


class YNV_OT_ComputeBBox(Operator):
    """Recalcule la bounding box depuis le mesh"""
    bl_idname  = "gta5_ynv.compute_bbox"; bl_label = "Calculer BB"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props    = context.scene.gta5_pathing.ynv
        poly_obj = next((o for o in context.scene.objects if o.get("ynv_type") == "poly_mesh"), None)
        if poly_obj is None or poly_obj.type != "MESH":
            self.report({"WARNING"}, "Aucun mesh YNV"); return {"CANCELLED"}
        verts = [poly_obj.matrix_world @ v.co for v in poly_obj.data.vertices]
        if not verts: return {"CANCELLED"}
        props.bb_min = (min(v.x for v in verts), min(v.y for v in verts), min(v.z for v in verts))
        props.bb_max = (max(v.x for v in verts), max(v.y for v in verts), max(v.z for v in verts))
        self.report({"INFO"}, "Bounding Box calculée.")
        return {"FINISHED"}


class YNV_OT_SplitMesh(Operator):
    """Découpe le mesh selon la grille Tile Size / Offset"""
    bl_idname  = "gta5_ynv.split_mesh"; bl_label = "Split Mesh"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        self.report({"INFO"}, "Split Mesh : utiliser un outil externe (CodeWalker) pour le découpage en tuiles.")
        return {"FINISHED"}


_classes = [
    YNV_OT_Import, YNV_OT_Export,
    YNV_OT_ReadSelectedFlags, YNV_OT_ApplyFlagsPreset, YNV_OT_ApplyCustomFlags,
    YNV_OT_AddPolygon,
    YNV_OT_AddPortal,    YNV_OT_RemovePortal,
    YNV_OT_AddNavPoint,  YNV_OT_RemoveNavPoint,
    YNV_OT_SyncFromObjects, YNV_OT_ComputeBBox, YNV_OT_SplitMesh,
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
