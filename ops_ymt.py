"""ops_ymt.py — Scenario YMT : Import / Nouveau / Export complet"""
import bpy, xml.etree.ElementTree as ET
from bpy.types import Operator
from bpy.props import StringProperty, IntProperty, BoolProperty
from .xmlio import geti, gets, getb, get_xyz, get_xyzw, seti, sets_el, setb_el, set_xyz_el, set_xyzw_el, to_xml_string
from .props import ITYPE_NAMES

COL = "GTA5_Scenarios"

def _col():
    c=bpy.data.collections.get(COL)
    if not c: c=bpy.data.collections.new(COL); bpy.context.scene.collection.children.link(c)
    return c

def _link(obj,col):
    for c in obj.users_collection: c.objects.unlink(obj)
    col.objects.link(obj)

def _clear():
    col=bpy.data.collections.get(COL)
    if col:
        for o in list(col.objects): bpy.data.objects.remove(o,do_unlink=True)

def _update_stats(props):
    props.stat_points=len(props.points); props.stat_cn=len(props.chain_nodes)
    props.stat_ce=len(props.chain_edges); props.stat_chains=len(props.chains)

def _parse(filepath,props):
    props.points.clear(); props.chain_nodes.clear(); props.chain_edges.clear()
    props.chains.clear(); props.entity_overrides.clear(); props.clusters.clear()
    try:   root=ET.parse(filepath).getroot()
    except Exception as e: return False,str(e)
    if root.tag!="CScenarioPointRegion": return False,f"Tag attendu CScenarioPointRegion, trouvé {root.tag}"
    props.version_number=geti(root,"VersionNumber",80)

    # Scenario Points
    pts_sec=root.find("Points")
    if pts_sec is not None:
        my_pts=pts_sec.find("MyPoints")
        if my_pts is not None:
            for item in my_pts.findall("Item"):
                sp=props.points.add()
                sp.itype=geti(item,"iType",1); sp.model_set_id=geti(item,"ModelSetId",0)
                sp.interior_id=geti(item,"iInterior",0); sp.imap_id=geti(item,"iRequiredIMapId",0)
                sp.probability=geti(item,"iProbability",0); sp.avail_mp_sp=geti(item,"uAvailableInMpSp",3)
                sp.time_start=geti(item,"iTimeStartOverride",0); sp.time_end=geti(item,"iTimeEndOverride",24)
                sp.radius=geti(item,"iRadius",0); sp.time_till_leaves=geti(item,"iTimeTillPedLeaves",255)
                sp.scenario_group=geti(item,"iScenarioGroup",0)
                fe=item.find("Flags"); sp.flags=(fe.text or "").strip() if fe is not None else ""
                pe=item.find("vPositionAndDirection")
                if pe is not None:
                    sp.position=(float(pe.get("x",0)),float(pe.get("y",0)),float(pe.get("z",0)),float(pe.get("w",0)))

    # Entity Overrides
    eo_sec=root.find("EntityOverrides")
    if eo_sec is not None:
        for item in eo_sec.findall("Item"):
            eo=props.entity_overrides.add()
            et_el=item.find("EntityType"); eo.entity_type=(et_el.text or "").strip() if et_el is not None else ""
            ep=item.find("EntityPosition")
            if ep is not None: eo.entity_position=(float(ep.get("x",0)),float(ep.get("y",0)),float(ep.get("z",0)))
            eo.may_not_exist=getb(item,"EntityMayNotAlwaysExist",True)
            eo.prevent_art  =getb(item,"SpecificallyPreventArtPoints",False)

    # ChainingGraph
    cg=root.find("ChainingGraph")
    if cg is not None:
        for item in (cg.find("Nodes") or []):
            cn=props.chain_nodes.add()
            pos=item.find("Position")
            if pos is not None: cn.position=(float(pos.get("x",0)),float(pos.get("y",0)),float(pos.get("z",0)))
            hb=item.find("hash_9B1D60AB"); cn.hash_9b=(hb.text or "").strip() if hb is not None else ""
            st=item.find("ScenarioType"); cn.scenario_type=(st.text or "standing").strip() if st is not None else "standing"
            hi=item.find("HasIncomingEdges"); cn.has_incoming=(hi.get("value","false").lower()=="true") if hi is not None else False
            ho=item.find("HasOutgoingEdges"); cn.has_outgoing=(ho.get("value","true").lower()=="true") if ho is not None else True
        for item in (cg.find("Edges") or []):
            ce=props.chain_edges.add(); ce.node_from=geti(item,"NodeIndexFrom",0); ce.node_to=geti(item,"NodeIndexTo",0)
            ce.action=geti(item,"Action",0); ce.nav_mode=geti(item,"NavMode",1); ce.nav_speed=geti(item,"NavSpeed",2)
        for item in (cg.find("Chains") or []):
            ch=props.chains.add()
            hk=item.find("hash_44F1B77A"); ch.hash_name=hk.get("value","1") if hk is not None else "1"
            ei=item.find("EdgeIds"); ch.edge_ids=(ei.text or "").strip() if ei is not None else ""

    # AccelGrid
    ag=root.find("AccelGrid")
    if ag is not None:
        props.ag_min_cell_x=geti(ag,"MinCellX",-4); props.ag_max_cell_x=geti(ag,"MaxCellX",5)
        props.ag_min_cell_y=geti(ag,"MinCellY",-64); props.ag_max_cell_y=geti(ag,"MaxCellY",-48)
        props.ag_cell_dim_x=geti(ag,"CellDimX",32); props.ag_cell_dim_y=geti(ag,"CellDimY",32)

    # Clusters
    cl_sec=root.find("Clusters")
    if cl_sec is not None:
        for item in cl_sec.findall("Item"):
            cl=props.clusters.add()
            cs=item.find("ClusterSphere")
            if cs is not None:
                cr=cs.find("centerAndRadius")
                if cr is not None:
                    cl.center_x=float(cr.get("x",0)); cl.center_y=float(cr.get("y",0))
                    cl.center_z=float(cr.get("z",0)); cl.radius=float(cr.get("w",1))
            h4=item.find("hash_4151BB75"); cl.hash_4151=int(h4.get("value",0)) if h4 is not None else 0
            hb=item.find("hash_BA87159C"); cl.hash_ba87=(hb.get("value","false").lower()=="true") if hb is not None else False

    # LookUps
    lu=root.find("LookUps")
    if lu is not None:
        def _lu(tag):
            sec=lu.find(tag)
            if sec is None: return ""
            return "\n".join((i.text or "").strip() for i in sec.findall("Item"))
        props.lu_type_names=_lu("TypeNames"); props.lu_ped_models=_lu("PedModelSetNames")
        props.lu_veh_models=_lu("VehicleModelSetNames"); props.lu_group_names=_lu("GroupNames")
        props.lu_interior_names=_lu("InteriorNames"); props.lu_imap_names=_lu("RequiredIMapNames")

    _update_stats(props); return True,"OK"

def _build_objects(props,col,filename="scenario.ymt"):
    root_obj=bpy.data.objects.new(filename,None); root_obj.empty_display_type="PLAIN_AXES"; root_obj["ymt_type"]="root"; _link(root_obj,col)
    sp_root=bpy.data.objects.new("YMT_Points",None); sp_root.empty_display_type="PLAIN_AXES"; sp_root.parent=root_obj; _link(sp_root,col)
    for i,sp in enumerate(props.points):
        name=ITYPE_NAMES.get(sp.itype,f"t{sp.itype}")
        obj=bpy.data.objects.new(f"YMT_SP{i}_{name}",None); obj.empty_display_type="SINGLE_ARROW"; obj.empty_display_size=1.0
        obj.location=(sp.position[0],sp.position[1],sp.position[2]); obj.rotation_euler=(0,0,sp.position[3])
        obj["ymt_type"]="sp"; obj["sp_idx"]=i; obj["itype"]=sp.itype; obj.parent=sp_root; _link(obj,col)
    cn_root=bpy.data.objects.new("YMT_ChainingNodes",None); cn_root.empty_display_type="PLAIN_AXES"; cn_root.parent=root_obj; _link(cn_root,col)
    for i,cn in enumerate(props.chain_nodes):
        obj=bpy.data.objects.new(f"YMT_CN{i}_{cn.scenario_type[:8]}",None); obj.empty_display_type="CIRCLE"; obj.empty_display_size=0.5
        obj.location=cn.position; obj["ymt_type"]="cn"; obj["cn_idx"]=i; obj.parent=cn_root; _link(obj,col)

def _export(ctx,props):
    # Sync depuis objets
    for obj in ctx.scene.objects:
        if obj.get("ymt_type")=="sp":
            idx=obj.get("sp_idx",-1)
            if 0<=idx<len(props.points):
                sp=props.points[idx]; sp.position=(obj.location.x,obj.location.y,obj.location.z,obj.rotation_euler.z)
        elif obj.get("ymt_type")=="cn":
            idx=obj.get("cn_idx",-1)
            if 0<=idx<len(props.chain_nodes): props.chain_nodes[idx].position=tuple(obj.location)

    root=ET.Element("CScenarioPointRegion"); seti(root,"VersionNumber",props.version_number)

    pts_el=ET.SubElement(root,"Points")
    ET.SubElement(pts_el,"LoadSavePoints",itemType="CExtensionDefSpawnPoint")
    my=ET.SubElement(pts_el,"MyPoints",itemType="CScenarioPoint")
    for sp in props.points:
        item=ET.SubElement(my,"Item")
        seti(item,"iType",sp.itype); seti(item,"ModelSetId",sp.model_set_id)
        seti(item,"iInterior",sp.interior_id); seti(item,"iRequiredIMapId",sp.imap_id)
        seti(item,"iProbability",sp.probability); seti(item,"uAvailableInMpSp",sp.avail_mp_sp)
        seti(item,"iTimeStartOverride",sp.time_start); seti(item,"iTimeEndOverride",sp.time_end)
        seti(item,"iRadius",sp.radius); seti(item,"iTimeTillPedLeaves",sp.time_till_leaves)
        seti(item,"iScenarioGroup",sp.scenario_group); ET.SubElement(item,"Flags").text=sp.flags
        pos=ET.SubElement(item,"vPositionAndDirection")
        pos.set("x",f"{sp.position[0]:.7g}"); pos.set("y",f"{sp.position[1]:.7g}")
        pos.set("z",f"{sp.position[2]:.7g}"); pos.set("w",f"{sp.position[3]:.7g}")

    eo_el=ET.SubElement(root,"EntityOverrides",itemType="CScenarioEntityOverride")
    for eo in props.entity_overrides:
        item=ET.SubElement(eo_el,"Item")
        ep=ET.SubElement(item,"EntityPosition")
        ep.set("x",f"{eo.entity_position[0]:.7g}"); ep.set("y",f"{eo.entity_position[1]:.7g}"); ep.set("z",f"{eo.entity_position[2]:.7g}")
        ET.SubElement(item,"EntityType").text=eo.entity_type
        ET.SubElement(item,"ScenarioPoints",itemType="CExtensionDefSpawnPoint")
        setb_el(item,"EntityMayNotAlwaysExist",eo.may_not_exist); setb_el(item,"SpecificallyPreventArtPoints",eo.prevent_art)

    cg_el=ET.SubElement(root,"ChainingGraph")
    nd_el=ET.SubElement(cg_el,"Nodes",itemType="CScenarioChainingNode")
    for cn in props.chain_nodes:
        item=ET.SubElement(nd_el,"Item")
        pos=ET.SubElement(item,"Position"); pos.set("x",f"{cn.position[0]:.7g}"); pos.set("y",f"{cn.position[1]:.7g}"); pos.set("z",f"{cn.position[2]:.7g}")
        ET.SubElement(item,"hash_9B1D60AB").text=cn.hash_9b
        ET.SubElement(item,"ScenarioType").text=cn.scenario_type
        setb_el(item,"HasIncomingEdges",cn.has_incoming); setb_el(item,"HasOutgoingEdges",cn.has_outgoing)
    ce_el=ET.SubElement(cg_el,"Edges",itemType="CScenarioChainingEdge")
    for ce in props.chain_edges:
        item=ET.SubElement(ce_el,"Item"); seti(item,"NodeIndexFrom",ce.node_from); seti(item,"NodeIndexTo",ce.node_to)
        seti(item,"Action",ce.action); seti(item,"NavMode",ce.nav_mode); seti(item,"NavSpeed",ce.nav_speed)
    ch_el=ET.SubElement(cg_el,"Chains",itemType="CScenarioChain")
    for ch in props.chains:
        item=ET.SubElement(ch_el,"Item"); ET.SubElement(item,"hash_44F1B77A").set("value",ch.hash_name)
        ET.SubElement(item,"EdgeIds").text=ch.edge_ids

    ag_el=ET.SubElement(root,"AccelGrid")
    seti(ag_el,"MinCellX",props.ag_min_cell_x); seti(ag_el,"MaxCellX",props.ag_max_cell_x)
    seti(ag_el,"MinCellY",props.ag_min_cell_y); seti(ag_el,"MaxCellY",props.ag_max_cell_y)
    seti(ag_el,"CellDimX",props.ag_cell_dim_x); seti(ag_el,"CellDimY",props.ag_cell_dim_y)

    ET.SubElement(root,"hash_E529D603")

    cl_el=ET.SubElement(root,"Clusters",itemType="CScenarioPointCluster")
    for cl in props.clusters:
        item=ET.SubElement(cl_el,"Item")
        pts_cl=ET.SubElement(item,"Points",itemType="CExtensionDefSpawnPoint")
        cs=ET.SubElement(item,"ClusterSphere"); cr=ET.SubElement(cs,"centerAndRadius")
        cr.set("x",f"{cl.center_x:.7g}"); cr.set("y",f"{cl.center_y:.7g}"); cr.set("z",f"{cl.center_z:.7g}"); cr.set("w",f"{cl.radius:.7g}")
        seti(item,"hash_4151BB75",cl.hash_4151); setb_el(item,"hash_BA87159C",cl.hash_ba87)

    lu_el=ET.SubElement(root,"LookUps")
    def _wlu(tag,s):
        sec=ET.SubElement(lu_el,tag)
        for name in s.split("\n"):
            name=name.strip()
            if name: ET.SubElement(sec,"Item").text=name
    _wlu("TypeNames",props.lu_type_names); _wlu("PedModelSetNames",props.lu_ped_models)
    _wlu("VehicleModelSetNames",props.lu_veh_models); _wlu("GroupNames",props.lu_group_names)
    _wlu("InteriorNames",props.lu_interior_names); _wlu("RequiredIMapNames",props.lu_imap_names)
    return to_xml_string(root)

# ── Opérateurs ────────────────────────────────────────────────────────────────

class YMT_OT_Import(Operator):
    """Importe un fichier Scenario YMT XML"""
    bl_idname="gta5pe.ymt_import"; bl_label="Importer YMT"; bl_options={"REGISTER","UNDO"}
    filepath:StringProperty(subtype="FILE_PATH"); filter_glob:StringProperty(default="*.xml;*.ymt;*.ymt.xml",options={"HIDDEN"})
    def invoke(self,ctx,e): ctx.window_manager.fileselect_add(self); return{"RUNNING_MODAL"}
    def execute(self,ctx):
        import os as _os
        props=ctx.scene.gta5pe.ymt; ok,msg=_parse(self.filepath,props)
        if not ok: self.report({"ERROR"},msg); return{"CANCELLED"}
        filename=_os.path.basename(self.filepath)
        col_name="GTA5PE_YMT_"+_os.path.splitext(_os.path.splitext(filename)[0])[0]
        props["col_name"]=col_name
        props.filepath=self.filepath
        old=bpy.data.collections.get(col_name)
        if old:
            for o in list(old.objects): bpy.data.objects.remove(o,do_unlink=True)
            bpy.data.collections.remove(old)
        col=bpy.data.collections.new(col_name); bpy.context.scene.collection.children.link(col)
        _build_objects(props,col,filename)
        self.report({"INFO"},f"YMT: {props.stat_points} pts | {props.stat_cn} nodes | {props.stat_ce} edges | {props.stat_chains} chains")
        return{"FINISHED"}

class YMT_OT_New(Operator):
    """Crée un ScenarioPointRegion vide"""
    bl_idname="gta5pe.ymt_new"; bl_label="Nouveau YMT"; bl_options={"REGISTER","UNDO"}
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ymt; props.filepath=""
        props.points.clear(); props.chain_nodes.clear(); props.chain_edges.clear()
        props.chains.clear(); props.entity_overrides.clear(); props.clusters.clear(); _update_stats(props)
        _clear(); _col(); self.report({"INFO"},"Scenario vide créé"); return{"FINISHED"}

class YMT_OT_Export(Operator):
    """Exporte les Scenarios en .ymt.xml"""
    bl_idname="gta5pe.ymt_export"; bl_label="Exporter .ymt.xml"; bl_options={"REGISTER"}
    filepath:StringProperty(subtype="FILE_PATH"); filter_glob:StringProperty(default="*.xml;*.ymt;*.ymt.xml",options={"HIDDEN"})
    def invoke(self,ctx,e):
        import os; props=ctx.scene.gta5pe.ymt; base=props.filepath or "scenario.ymt.xml"
        if not (base.endswith(".ymt.xml") or base.endswith(".ymt")): base=os.path.splitext(base)[0]+".ymt.xml"
        self.filepath=base; ctx.window_manager.fileselect_add(self); return{"RUNNING_MODAL"}
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ymt; xml=_export(ctx,props)
        try:
            with open(self.filepath,"w",encoding="utf-8") as f: f.write(xml)
        except OSError as e: self.report({"ERROR"},str(e)); return{"CANCELLED"}
        props.filepath=self.filepath; self.report({"INFO"},f"YMT exporté → {self.filepath}"); return{"FINISHED"}

class YMT_OT_AddPt(Operator):
    """Ajoute un point de scénario au curseur"""
    bl_idname="gta5pe.ymt_add_pt"; bl_label="Ajouter point"; bl_options={"REGISTER","UNDO"}
    itype:IntProperty(name="iType",default=1,min=0,max=255)
    def invoke(self,ctx,e): return ctx.window_manager.invoke_props_dialog(self)
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ymt; sp=props.points.add()
        sp.itype=self.itype; sp.time_end=24; sp.avail_mp_sp=3; sp.time_till_leaves=255
        c=ctx.scene.cursor.location; sp.position=(c.x,c.y,c.z,0.0)
        props.point_idx=len(props.points)-1; props.stat_points=len(props.points)
        col=_col(); name=ITYPE_NAMES.get(self.itype,f"t{self.itype}"); i=props.point_idx
        obj=bpy.data.objects.new(f"YMT_SP{i}_{name}",None); obj.empty_display_type="SINGLE_ARROW"; obj.empty_display_size=1.0
        obj.location=(c.x,c.y,c.z); obj["ymt_type"]="sp"; obj["sp_idx"]=i; obj["itype"]=self.itype; _link(obj,col); return{"FINISHED"}

class YMT_OT_RemPt(Operator):
    """Supprime le point actif"""
    bl_idname="gta5pe.ymt_rem_pt"; bl_label="Supprimer point"; bl_options={"REGISTER","UNDO"}
    @classmethod
    def poll(cls,ctx): p=ctx.scene.gta5pe.ymt; return 0<=p.point_idx<len(p.points)
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ymt; props.points.remove(props.point_idx)
        props.point_idx=min(props.point_idx,len(props.points)-1); props.stat_points=len(props.points); return{"FINISHED"}

class YMT_OT_AddCN(Operator):
    """Ajoute un noeud de chaînage au curseur"""
    bl_idname="gta5pe.ymt_add_cn"; bl_label="Ajouter noeud chaînage"; bl_options={"REGISTER","UNDO"}
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ymt; cn=props.chain_nodes.add()
        c=ctx.scene.cursor.location; cn.position=(c.x,c.y,c.z); cn.has_outgoing=True
        props.cn_idx=len(props.chain_nodes)-1; props.stat_cn=len(props.chain_nodes)
        col=_col(); i=props.cn_idx; obj=bpy.data.objects.new(f"YMT_CN{i}_standing",None)
        obj.empty_display_type="CIRCLE"; obj.empty_display_size=0.5; obj.location=cn.position
        obj["ymt_type"]="cn"; obj["cn_idx"]=i; _link(obj,col); return{"FINISHED"}

class YMT_OT_AddCE(Operator):
    """Ajoute une arête de chaînage"""
    bl_idname="gta5pe.ymt_add_ce"; bl_label="Ajouter arête"; bl_options={"REGISTER","UNDO"}
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ymt; ce=props.chain_edges.add(); ce.nav_mode=1; ce.nav_speed=2
        props.ce_idx=len(props.chain_edges)-1; props.stat_ce=len(props.chain_edges); return{"FINISHED"}

class YMT_OT_RemCE(Operator):
    """Supprime l'arête active"""
    bl_idname="gta5pe.ymt_rem_ce"; bl_label="Supprimer arête"; bl_options={"REGISTER","UNDO"}
    @classmethod
    def poll(cls,ctx): p=ctx.scene.gta5pe.ymt; return 0<=p.ce_idx<len(p.chain_edges)
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ymt; props.chain_edges.remove(props.ce_idx)
        props.ce_idx=min(props.ce_idx,len(props.chain_edges)-1); props.stat_ce=len(props.chain_edges); return{"FINISHED"}

class YMT_OT_RemNodeEdges(Operator):
    """Supprime toutes les arêtes du noeud actif"""
    bl_idname="gta5pe.ymt_rem_node_edges"; bl_label="Supprimer arêtes du noeud"; bl_options={"REGISTER","UNDO"}
    @classmethod
    def poll(cls,ctx): p=ctx.scene.gta5pe.ymt; return 0<=p.cn_idx<len(p.chain_nodes)
    def invoke(self,ctx,e): return ctx.window_manager.invoke_confirm(self,e)
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ymt; ni=props.cn_idx
        to_rem=[i for i,e in enumerate(props.chain_edges) if e.node_from==ni or e.node_to==ni]
        for i in reversed(to_rem): props.chain_edges.remove(i)
        props.ce_idx=min(props.ce_idx,len(props.chain_edges)-1); props.stat_ce=len(props.chain_edges)
        self.report({"INFO"},f"{len(to_rem)} arête(s) supprimée(s)"); return{"FINISHED"}

class YMT_OT_Sync(Operator):
    """Synchronise depuis les empties Blender"""
    bl_idname="gta5pe.ymt_sync"; bl_label="Sync depuis objets"; bl_options={"REGISTER","UNDO"}
    def execute(self,ctx):
        props=ctx.scene.gta5pe.ymt; cnt=0
        for obj in ctx.scene.objects:
            if obj.get("ymt_type")=="sp":
                idx=obj.get("sp_idx",-1)
                if 0<=idx<len(props.points):
                    sp=props.points[idx]; sp.position=(obj.location.x,obj.location.y,obj.location.z,obj.rotation_euler.z); cnt+=1
            elif obj.get("ymt_type")=="cn":
                idx=obj.get("cn_idx",-1)
                if 0<=idx<len(props.chain_nodes): props.chain_nodes[idx].position=tuple(obj.location); cnt+=1
        self.report({"INFO"},f"{cnt} objet(s) synchronisé(s)"); return{"FINISHED"}




class YMT_OT_ToggleFlag(Operator):
    """Toggle a scenario point flag on/off"""
    bl_idname="gta5pe.ymt_toggle_flag"; bl_label="Toggle Scenario Flag"
    bl_options={"REGISTER","UNDO"}
    flag_name: StringProperty(name="Flag", default="NoSpawn")

    @classmethod
    def poll(cls,ctx): p=ctx.scene.gta5pe.ymt; return 0<=p.point_idx<len(p.points)

    def execute(self,ctx):
        props=ctx.scene.gta5pe.ymt
        pt=props.points[props.point_idx]
        current=pt.flags.strip()
        flags_list=[f.strip() for f in current.split(",") if f.strip()] if current else []
        if self.flag_name in flags_list:
            flags_list.remove(self.flag_name)
            action="removed"
        else:
            flags_list.append(self.flag_name)
            action="added"
        pt.flags=", ".join(flags_list)
        self.report({"INFO"},f"Flag '{self.flag_name}' {action}. Current: {pt.flags or 'none'}")
        return{"FINISHED"}

class YMT_OT_TrackActive(Operator):
    """Modal: follow active object to update scenario point selection."""
    bl_idname="gta5pe.ymt_track_active"; bl_label="Track Active YMT Object"
    bl_options=set()
    _last=None
    def modal(self,ctx,event):
        if not hasattr(ctx.scene,"gta5pe"): return{"CANCELLED"}
        if ctx.scene.gta5pe.tab!="YMT": return{"PASS_THROUGH"}
        if event.type not in ("LEFTMOUSE","MOUSEMOVE","TIMER"): return{"PASS_THROUGH"}
        obj=ctx.active_object
        if obj is self.__class__._last: return{"PASS_THROUGH"}
        self.__class__._last=obj
        props=ctx.scene.gta5pe.ymt
        if obj and obj.get("ymt_type")=="sp":
            idx=obj.get("sp_idx",-1)
            if 0<=idx<len(props.points) and props.point_idx!=idx:
                props.point_idx=idx
                for a in ctx.screen.areas: a.tag_redraw()
        elif obj and obj.get("ymt_type")=="cn":
            idx=obj.get("cn_idx",-1)
            if 0<=idx<len(props.chain_nodes) and props.cnode_idx!=idx:
                props.cnode_idx=idx
                for a in ctx.screen.areas: a.tag_redraw()
        return{"PASS_THROUGH"}
    def invoke(self,ctx,e):
        ctx.window_manager.modal_handler_add(self); return{"RUNNING_MODAL"}

_CLASSES=[YMT_OT_Import,YMT_OT_New,YMT_OT_Export,YMT_OT_AddPt,YMT_OT_RemPt,
          YMT_OT_AddCN,YMT_OT_AddCE,YMT_OT_RemCE,YMT_OT_RemNodeEdges,YMT_OT_Sync, YMT_OT_ToggleFlag, YMT_OT_TrackActive]

def register():
    for cls in _CLASSES:
        try: bpy.utils.unregister_class(cls)
        except: pass
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_CLASSES):
        try: bpy.utils.unregister_class(cls)
        except: pass
