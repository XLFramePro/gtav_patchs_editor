"""
operators_trains.py — Opérateurs Import/Export/Édition pour les voies de train (trains*.dat).

Format trains*.dat :
  Ligne 1 : nombre de points (int)
  Lignes suivantes : X Y Z FLAG
    FLAG = 0  : point de voie normal
    FLAG = 4  : aiguillage / junction (le train peut bifurquer)
    FLAG = 1/5: variations rares (parfois utilisées pour des segments spéciaux)

La piste est une courbe 3D continue. Les aiguillages permettent de créer
des réseaux de train complexes avec des bifurcations.
"""

import bpy
import os
import math
from bpy.types import Operator
from bpy.props import StringProperty, IntProperty, BoolProperty, EnumProperty
from mathutils import Vector


# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

TRAINS_COLLECTION = "TRAINS_TrackEditor"
TRACK_COLOR       = (0.2, 0.2, 0.2, 1.0)   # gris foncé = rail
JUNCTION_COLOR    = (1.0, 0.4, 0.0, 1.0)   # orange = aiguillage


# ─────────────────────────────────────────────────────────────────────────────
#  PARSE .DAT
# ─────────────────────────────────────────────────────────────────────────────

def _parse_trains_dat(filepath, props):
    """Parse le fichier trains*.dat et remplit la collection de points."""
    props.points.clear()

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
    except OSError as e:
        return False, f"Lecture impossible : {e}"

    if not lines:
        return False, "Fichier vide."

    # Première ligne = nombre de points attendus
    try:
        expected = int(lines[0])
    except ValueError:
        return False, f"Ligne 1 invalide (attendu entier) : '{lines[0]}'"

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
    """Reconstruit le fichier .dat depuis les données Blender."""
    # Sync depuis la courbe Blender si elle existe
    curve_obj = next((o for o in context.scene.objects
                      if o.get("trains_type") == "track_curve"), None)

    if curve_obj and curve_obj.type == "CURVE":
        # Extraire les points de la courbe
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

    # Ecrire le DAT
    n = len(props.points)
    lines = [str(n)]
    for pt in props.points:
        x, y, z = pt.position
        lines.append(f"{x:.3f} {y:.3f} {z:.3f} {pt.flag}")
    return "\r\n".join(lines) + "\r\n"


# ─────────────────────────────────────────────────────────────────────────────
#  CRÉATION OBJETS BLENDER
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
    """Crée un objet Courbe Blender représentant la voie de train."""
    curve_data = bpy.data.curves.new("TRAINS_TrackCurve", type="CURVE")
    curve_data.dimensions    = "3D"
    curve_data.resolution_u  = 4
    curve_data.bevel_depth   = 0.1
    curve_data.bevel_resolution = 0

    # Créer un spline poly avec tous les points
    spline = curve_data.splines.new("POLY")
    n = len(props.points)
    spline.points.add(n - 1)

    for i, pt in enumerate(props.points):
        spline.points[i].co = (*pt.position, 1.0)
        # Stocker le flag dans le radius pour récupération ultérieure
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
    """Crée des empties orange sur les aiguillages."""
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
#  OPÉRATEURS
# ─────────────────────────────────────────────────────────────────────────────

class TRAINS_OT_Import(Operator):
    """Importe un fichier trains*.dat dans Blender"""
    bl_idname  = "gta5_trains.import_dat"
    bl_label   = "Importer trains.dat"
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
                    f"Train importé : {props.stat_points} points, "
                    f"{props.stat_junctions} aiguillages — '{props.track_name}'")
        return {"FINISHED"}


class TRAINS_OT_Export(Operator):
    """Exporte la voie de train en fichier .dat"""
    bl_idname  = "gta5_trains.export_dat"
    bl_label   = "Exporter trains.dat"
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
            self.report({"ERROR"}, f"Écriture impossible : {e}")
            return {"CANCELLED"}
        props.filepath = self.filepath
        self.report({"INFO"}, f"Trains exporté ({len(props.points)} pts) → {self.filepath}")
        return {"FINISHED"}


class TRAINS_OT_AddPoint(Operator):
    """Ajoute un point de voie au curseur 3D"""
    bl_idname  = "gta5_trains.add_point"
    bl_label   = "Ajouter Point"
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

        # Ajouter le point à la courbe existante
        curve_obj = next((o for o in context.scene.objects
                          if o.get("trains_type") == "track_curve"), None)
        if curve_obj and curve_obj.type == "CURVE":
            spline = curve_obj.data.splines[0]
            spline.points.add(1)
            spline.points[-1].co = (*pt.position, 1.0)
            spline.points[-1].radius = float(pt.flag)
        return {"FINISHED"}


class TRAINS_OT_RemovePoint(Operator):
    """Supprime le point de voie sélectionné"""
    bl_idname  = "gta5_trains.remove_point"
    bl_label   = "Supprimer Point"
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
    """Marque le point sélectionné comme aiguillage (flag=4)"""
    bl_idname  = "gta5_trains.mark_junction"
    bl_label   = "Marquer Aiguillage"
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
        self.report({"INFO"}, f"Point {props.point_index}: flag={'4 (aiguillage)' if pt.flag==4 else '0 (normal)'}")
        return {"FINISHED"}


class TRAINS_OT_SyncFromCurve(Operator):
    """Synchronise les points depuis la courbe Blender"""
    bl_idname  = "gta5_trains.sync_from_curve"
    bl_label   = "Sync depuis Courbe"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.gta5_pathing.trains
        curve_obj = next((o for o in context.scene.objects
                          if o.get("trains_type") == "track_curve"), None)
        if curve_obj is None or curve_obj.type != "CURVE":
            self.report({"WARNING"}, "Aucune courbe de train trouvée.")
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
        self.report({"INFO"}, f"Sync : {count} points extraits de la courbe")
        return {"FINISHED"}


class TRAINS_OT_GenerateFromCurve(Operator):
    """Génère une voie de train depuis un objet Courbe sélectionné"""
    bl_idname  = "gta5_trains.generate_from_curve"
    bl_label   = "Générer depuis Courbe Sélectionnée"
    bl_options = {"REGISTER", "UNDO"}

    resolution: IntProperty(
        name="Résolution",
        description="Nombre de points par unité Blender",
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

        # Évaluer la courbe pour obtenir un mesh
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

        # Marquer le tag track_curve sur l'objet
        obj["trains_type"] = "track_curve"
        obj["track_name"]  = obj.name

        self.report({"INFO"}, f"Voie générée : {props.stat_points} points")
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
