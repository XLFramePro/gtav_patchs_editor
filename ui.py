"""
ui.py — N-Panel GTA V Pathing Editor with complete YND panel
(flags structured NodeFlags0-5, LinkFlags0-2, reference design ynd.rar).
"""
import bpy
from bpy.types import Panel, UIList


# ── UI LISTS ──────────────────────────────────────────────────────────────────

class GTA5_UL_YNV_Portals(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        layout.label(text=f"[T{item.portal_type}] Poly {item.poly_from}→{item.poly_to}", icon="OBJECT_DATA")

class GTA5_UL_YNV_NavPoints(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        layout.label(text=f"[T{item.point_type}] ({item.position[0]:.0f},{item.position[1]:.0f},{item.position[2]:.0f})", icon="EMPTY_SINGLE_ARROW")

class GTA5_UL_YND_Nodes(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        from .properties import PED_SPECIAL_TYPES
        is_ped = item.flags1.special_type in PED_SPECIAL_TYPES
        ic = "USER" if is_ped else "AUTO"
        sp = item.flags1.special_type
        name = item.street_name or f"Node_{item.node_id}"
        lk_count = len(item.links)
        row = layout.row(align=True)
        row.label(text=f"[{item.area_id}:{item.node_id}] {name}", icon=ic)
        row.label(text=f"{lk_count}lk  {sp[:6] if sp!='NONE' else ''}")

class GTA5_UL_YND_Links(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        f2 = item.flags2
        fwd = f2.forward_lanes; bk = f2.back_lanes
        dead = "💀" if item.flags1.dead_end else ""
        gps  = "🛰" if item.flags0.gps_both_ways else ""
        layout.label(
            text=f"→{item.to_area_id}:{item.to_node_id}  L={item.link_length}  F{fwd}B{bk}{dead}{gps}",
            icon="LINKED"
        )

class GTA5_UL_YMT_ScenarioPoints(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        from .operators_ymt import ITYPE_NAMES
        tname = ITYPE_NAMES.get(item.itype, f"t{item.itype}")
        layout.label(text=f"[{item.itype}:{tname}] ({item.position[0]:.0f},{item.position[1]:.0f})", icon="EMPTY_SINGLE_ARROW")

class GTA5_UL_YMT_ChainingNodes(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        layout.label(text=f"[{index}] {item.scenario_type}", icon="TRIA_RIGHT" if item.has_outgoing else "DOT")

class GTA5_UL_YMT_ChainingEdges(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        layout.label(text=f"{item.node_from}→{item.node_to}  spd={item.nav_speed}", icon="CURVE_PATH")

class GTA5_UL_TRAINS_Points(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        ic = "DECORATE_DRIVER" if item.flag == 4 else "CURVE_PATH"
        layout.label(text=f"{index}: ({item.position[0]:.1f},{item.position[1]:.1f},{item.position[2]:.1f}){' [JCT]' if item.flag==4 else ''}", icon=ic)


# ── PANNEAU PRINCIPAL ─────────────────────────────────────────────────────────

class GTA5_PT_PathingEditor(Panel):
    bl_label       = "GTA V Pathing Editor"
    bl_idname      = "GTA5_PT_pathing_editor"
    bl_space_type  = "VIEW_3D"
    bl_region_type = "UI"
    bl_category    = "GTA5 Paths"

    def draw(self, context):
        layout = self.layout
        if not hasattr(context.scene, "gta5_pathing"):
            layout.label(text="Addon not loaded.", icon="ERROR"); return
        gp = context.scene.gta5_pathing
        row = layout.row(align=True)
        row.prop(gp, "active_module", expand=True)
        layout.separator(factor=0.3)
        if   gp.active_module == "YNV":    _draw_ynv(layout, context, gp.ynv)
        elif gp.active_module == "YND":    _draw_ynd(layout, context, gp.ynd)
        elif gp.active_module == "YMT":    _draw_ymt(layout, context, gp.ymt)
        elif gp.active_module == "TRAINS": _draw_trains(layout, context, gp.trains)


# ── YNV ──────────────────────────────────────────────────────────────────────

def _draw_ynv(layout, context, props):
    row = layout.row(align=True)
    row.operator("gta5_ynv.import_xml", text="📂 Import YNV", icon="IMPORT")
    row.operator("gta5_ynv.export_xml", text="💾 Export YNV", icon="EXPORT")

    box = layout.box()
    box.label(text=f"NavMesh — Area {props.area_id}", icon="MOD_FLUID")
    col = box.column(align=True)
    col.label(text=f"Polygons : {props.stat_polygons}")
    col.label(text=f"Portals  : {props.stat_portals}")
    col.label(text=f"Nav Pts  : {props.stat_navpoints}")
    row = box.row(align=True); row.prop(props, "area_id")
    row2 = box.row(align=True); row2.prop(props, "bb_min", text="BB Min")
    row3 = box.row(align=True); row3.prop(props, "bb_max", text="BB Max")
    box.operator("gta5_ynv.compute_bbox", text="Recalculer BB", icon="CUBE")

    box_v = layout.box()
    box_v.label(text="Display", icon="HIDE_OFF")
    row = box_v.row(align=True)
    row.prop(props, "show_polygons", toggle=True)
    row.prop(props, "show_portals",  toggle=True)
    row.prop(props, "show_navpoints",toggle=True)

    layout.separator(factor=0.3)
    box_f = layout.box()
    box_f.label(text="Polygon Flags Editor", icon="TOOL_SETTINGS")
    row = box_f.row(align=True)
    row.prop(props, "flag_preset", text="Preset")
    row2 = box_f.row(align=True)
    row2.operator("gta5_ynv.apply_flags_preset", text="Apply Preset", icon="CHECKMARK")
    row2.operator("gta5_ynv.add_polygon",        text="+ Polygon",       icon="ADD")
    box_f.separator(factor=0.2)
    box_f.label(text="Custom Flags (select face in Edit Mode):")
    row_rd = box_f.row(align=True)
    row_rd.operator("gta5_ynv.read_selected_flags", text="Read Selection",     icon="EYEDROPPER")
    row_rd.operator("gta5_ynv.apply_custom_flags",  text="Apply Custom",   icon="CHECKMARK")

    pf = props.selected_poly_flags
    b0 = box_f.box(); b0.label(text="Flags1 — Surface (Byte 0)")
    g0 = b0.column_flow(columns=2, align=True)
    for a in ["small_poly","large_poly","is_pavement","is_underground","unused_f1_4","unused_f1_5","is_too_steep","is_water"]:
        g0.prop(pf, a)

    b1 = box_f.box(); b1.label(text="Flags2 — Audio/Props (Byte 1)")
    g1 = b1.column_flow(columns=2, align=True)
    for a in ["audio_prop1","audio_prop2","audio_prop3","unused_f2_3","near_car_node","is_interior","is_isolated","unused_f2_7"]:
        g1.prop(pf, a)

    b2 = box_f.box(); b2.label(text="Flags3 — Behavior (Byte 2)")
    g2 = b2.column_flow(columns=2, align=True)
    for a in ["can_spawn","is_road","along_edge","is_train_track","is_shallow","ped_density1","ped_density2","ped_density3"]:
        g2.prop(pf, a)

    b3 = box_f.box(); b3.label(text="Flags4 — Cover (Byte 3)")
    g3 = b3.column_flow(columns=2, align=True)
    for a in ["cover_south","cover_south2","cover_east","cover_north","cover_north2","cover_north3","cover_west","cover_south3"]:
        g3.prop(pf, a)

    b45 = box_f.box(); b45.label(text="Bytes 4-5 (internal density/audio)")
    r45 = b45.row(align=True); r45.prop(pf, "byte4"); r45.prop(pf, "byte5")

    layout.separator(factor=0.2)
    box_mc = layout.box(); box_mc.label(text="Mesh Cutter", icon="MOD_DECIM")
    col_mc = box_mc.column(align=True)
    col_mc.prop(props, "tile_size"); col_mc.prop(props, "offset_x"); col_mc.prop(props, "offset_y")
    box_mc.operator("gta5_ynv.split_mesh", text="Split Mesh", icon="MOD_EXPLODE")

    layout.separator(factor=0.2)
    box_p = layout.box(); box_p.label(text=f"Portals ({props.stat_portals})", icon="OBJECT_DATA")
    row2 = box_p.row()
    row2.template_list("GTA5_UL_YNV_Portals","",props,"portals",props,"portal_index",rows=3)
    col = row2.column(align=True)
    col.operator("gta5_ynv.add_portal",    text="",icon="ADD")
    col.operator("gta5_ynv.remove_portal", text="",icon="REMOVE")
    idx_p = props.portal_index
    if 0 <= idx_p < len(props.portals):
        p = props.portals[idx_p]; sub = box_p.box(); sub.label(text=f"Portal {idx_p}")
        sub.prop(p,"portal_type"); sub.prop(p,"angle"); sub.prop(p,"poly_from"); sub.prop(p,"poly_to")
        sub.prop(p,"pos_from"); sub.prop(p,"pos_to")

    layout.separator(factor=0.2)
    box_n = layout.box(); box_n.label(text=f"Nav Points ({props.stat_navpoints})", icon="EMPTY_SINGLE_ARROW")
    row2 = box_n.row()
    row2.template_list("GTA5_UL_YNV_NavPoints","",props,"nav_points",props,"nav_point_index",rows=3)
    col = row2.column(align=True)
    col.operator("gta5_ynv.add_nav_point",    text="",icon="ADD")
    col.operator("gta5_ynv.remove_nav_point", text="",icon="REMOVE")
    idx_n = props.nav_point_index
    if 0 <= idx_n < len(props.nav_points):
        np = props.nav_points[idx_n]; sub = box_n.box(); sub.label(text=f"Nav Point {idx_n}")
        sub.prop(np,"point_type"); sub.prop(np,"angle"); sub.prop(np,"position")
    box_n.operator("gta5_ynv.sync_from_objects", text="Sync from Empties", icon="FILE_REFRESH")


# ── YND ──────────────────────────────────────────────────────────────────────

def _draw_ynd(layout, context, props):
    row = layout.row(align=True)
    row.operator("gta5_ynd.import_xml", text="📂 Import YND", icon="IMPORT")
    row.operator("gta5_ynd.export_xml", text="💾 Export YND", icon="EXPORT")

    # Click-select button + Stats
    row_click = layout.row(align=True)
    row_click.operator("gta5_ynd.activate_click_select",
                       text="🖱 Activate Node Click-Select",
                       icon="CURSOR")

    box = layout.box()
    box.label(text=f"PathNodes — Area {props.area_id}", icon="EMPTY_ARROWS")
    col = box.column(align=True)
    col.label(text=f"Total     : {props.stat_nodes}")
    col.label(text=f"Vehicles : {props.stat_vehicle}  ●White  ■Green/Red")
    col.label(text=f"Pedestrians   : {props.stat_ped}   ●Grey   ──Red")
    col.label(text=f"Junctions: {props.stat_junctions}  □Purple")

    # Display
    box2 = layout.box(); box2.label(text="Display", icon="HIDE_OFF")
    row = box2.row(align=True)
    row.prop(props,"show_vehicle",  toggle=True)
    row.prop(props,"show_ped",      toggle=True)
    row.prop(props,"show_links",    toggle=True)
    row.prop(props,"show_junctions",toggle=True)
    box2.prop(props,"filter_street")
    box2.operator("gta5_ynd.sync_from_objects", text="Sync from Empties", icon="FILE_REFRESH")

    layout.separator(factor=0.2)

    # ── NODES LIST ─────────────────────────────────────────────────────
    box_n = layout.box(); box_n.label(text="Nodes", icon="EMPTY_ARROWS")
    row_add = box_n.row(align=True)
    row_add.operator("gta5_ynd.add_vehicle_node", text="+ Vehicle", icon="AUTO")
    row_add.operator("gta5_ynd.add_ped_node",     text="+ Pedestrian",   icon="USER")

    row2 = box_n.row()
    row2.template_list("GTA5_UL_YND_Nodes","",props,"nodes",props,"node_index",rows=6)
    col = row2.column(align=True)
    col.operator("gta5_ynd.remove_node", text="", icon="REMOVE")

    idx = props.node_index
    if 0 <= idx < len(props.nodes):
        node = props.nodes[idx]
        from .properties import PED_SPECIAL_TYPES
        is_ped = node.flags1.special_type in PED_SPECIAL_TYPES

        sub = box_n.box()
        sub.label(text=f"{'Pedestrian' if is_ped else 'Vehicle'} — {node.area_id}:{node.node_id}")
        row_id = sub.row(align=True)
        row_id.prop(node, "area_id"); row_id.prop(node, "node_id")
        sub.prop(node, "street_name")
        sub.prop(node, "position")

        # ── DETAILED FLAGS (like reference) ─────────────────────────────
        sub.separator(factor=0.2)
        sub.label(text="Node Flags :", icon="BOOKMARKS")

        # Flags1 — Special Type first (most important)
        box_f1 = sub.box()
        box_f1.label(text="Flags 1 — Special Type")
        box_f1.prop(node.flags1, "special_type")
        grid1 = box_f1.column_flow(columns=2, align=True)
        grid1.prop(node.flags1, "slip_lane")
        grid1.prop(node.flags1, "indicate_keep_left")
        grid1.prop(node.flags1, "indicate_keep_right")

        # Flags0
        box_f0 = sub.box(); box_f0.label(text="Flags 0 — Navigation")
        grid0 = box_f0.column_flow(columns=2, align=True)
        for a in ["scripted","gps_enabled","unused_4","offroad","unused_16","no_big_vehicles","cannot_go_right","cannot_go_left"]:
            grid0.prop(node.flags0, a)

        # Flags2
        box_f2 = sub.box(); box_f2.label(text="Flags 2 — Zone")
        grid2 = box_f2.column_flow(columns=2, align=True)
        for a in ["no_gps","unused_2","junction","unused_8","disabled_1","water_boats","freeway","disabled_2"]:
            grid2.prop(node.flags2, a)

        # Flags3-5 compact
        box_f35 = sub.box(); box_f35.label(text="Flags 3-4-5")
        row35 = box_f35.row(align=True)
        row35.prop(node.flags3, "tunnel")
        row35.prop(node.flags3, "heuristic")
        row_45 = box_f35.row(align=True)
        row_45.prop(node.flags4, "density")
        row_45.prop(node.flags4, "deadendness")
        row_45.prop(node.flags4, "left_turn_only")
        row_5 = box_f35.row(align=True)
        row_5.prop(node.flags5, "speed")
        row_5.prop(node.flags5, "has_junction_heightmap")

        # Junction heightmap if enabled
        if node.flags2.junction and node.flags5.has_junction_heightmap:
            box_jct = sub.box(); box_jct.label(text="Junction", icon="GRID")
            jct = node.junction
            row_j1 = box_jct.row(align=True)
            row_j1.prop(jct,"min_z"); row_j1.prop(jct,"max_z")
            row_j2 = box_jct.row(align=True)
            row_j2.prop(jct,"pos_x"); row_j2.prop(jct,"pos_y")
            row_j3 = box_jct.row(align=True)
            row_j3.prop(jct,"size_x"); row_j3.prop(jct,"size_y")
            box_jct.label(text="To generate heightmap: use CodeWalker", icon="ERROR")

        # ── NODE LINKS ───────────────────────────────────────────────────
        sub.separator(factor=0.2)
        sub2 = sub.box()
        sub2.label(text=f"Links ({len(node.links)})", icon="LINKED")

        row_lk_add = sub2.row(align=True)
        row_lk_add.operator("gta5_ynd.add_link",         text="+ Link",        icon="ADD")
        row_lk_add.operator("gta5_ynd.link_two_nodes",   text="Link to...",  icon="LINKED")
        row_lk_add.operator("gta5_ynd.remove_all_links", text="🗑 Remove All",   icon="TRASH")

        row3 = sub2.row()
        row3.template_list("GTA5_UL_YND_Links","",node,"links",node,"link_index",rows=4)
        col2 = row3.column(align=True)
        col2.operator("gta5_ynd.remove_link", text="", icon="REMOVE")

        li = node.link_index
        if 0 <= li < len(node.links):
            lk = node.links[li]
            sub3.label(text=f"Link {li} → {lk.to_area_id}:{lk.to_node_id}")

            row_lk = sub3.row(align=True)
            row_lk.prop(lk, "to_area_id", text="Area"); row_lk.prop(lk, "to_node_id", text="Node")
            sub3.label(text=f"Length : {lk.link_length}")

            # LinkFlags0
            bf0 = sub3.box(); bf0.label(text="Link Flags 0 — GPS")
            gf0 = bf0.column_flow(columns=2, align=True)
            gf0.prop(lk.flags0, "gps_both_ways")
            gf0.prop(lk.flags0, "block_if_no_lanes")
            gf0.prop(lk.flags0, "unknown_1")
            gf0.prop(lk.flags0, "unknown_2")

            # LinkFlags1
            bf1 = sub3.box(); bf1.label(text="Link Flags 1 — Route")
            gf1 = bf1.column_flow(columns=2, align=True)
            gf1.prop(lk.flags1, "unused_1")
            gf1.prop(lk.flags1, "narrow_road")
            gf1.prop(lk.flags1, "dead_end")
            gf1.prop(lk.flags1, "dead_end_exit")
            gf1.prop(lk.flags1, "negative_offset")
            gf1.prop(lk.flags1, "offset")

            # LinkFlags2
            bf2 = sub3.box(); bf2.label(text="Link Flags 2 — Lanes")
            gf2 = bf2.column_flow(columns=2, align=True)
            gf2.prop(lk.flags2, "dont_use_for_navigation")
            gf2.prop(lk.flags2, "shortcut")
            gf2.prop(lk.flags2, "back_lanes")
            gf2.prop(lk.flags2, "forward_lanes")


# ── YMT ──────────────────────────────────────────────────────────────────────

def _draw_ymt(layout, context, props):
    row = layout.row(align=True)
    row.operator("gta5_ymt.import_xml", text="📂 Import YMT", icon="IMPORT")
    row.operator("gta5_ymt.export_xml", text="💾 Export .ymt", icon="EXPORT")
    box = layout.box(); box.label(text=f"Scenarios v{props.version_number}", icon="ARMATURE_DATA")
    col = box.column(align=True)
    col.label(text=f"Points   : {props.stat_points}"); col.label(text=f"Nodes   : {props.stat_nodes}")
    col.label(text=f"Edges   : {props.stat_edges}");  col.label(text=f"Chains  : {props.stat_chains}")
    box2 = layout.box(); box2.label(text="Display", icon="FILTER")
    row = box2.row(align=True)
    row.prop(props,"show_scenario_pts",toggle=True); row.prop(props,"show_chain_nodes",toggle=True); row.prop(props,"show_chain_edges",toggle=True)
    box2.operator("gta5_ymt.sync_from_objects", text="Sync from Empties", icon="FILE_REFRESH")
    layout.separator(factor=0.2)
    box_sp = layout.box(); box_sp.label(text="Scenario Points", icon="EMPTY_SINGLE_ARROW")
    row2 = box_sp.row()
    row2.template_list("GTA5_UL_YMT_ScenarioPoints","",props,"scenario_points",props,"point_index",rows=5)
    col = row2.column(align=True)
    col.operator("gta5_ymt.add_scenario_point",    text="",icon="ADD")
    col.operator("gta5_ymt.remove_scenario_point", text="",icon="REMOVE")
    idx = props.point_index
    if 0 <= idx < len(props.scenario_points):
        sp = props.scenario_points[idx]; sub = box_sp.box(); sub.label(text=f"Point {idx}")
        sub.prop(sp,"itype"); sub.prop(sp,"flags")
        row_t = sub.row(align=True); row_t.prop(sp,"time_start",text="Start"); row_t.prop(sp,"time_end",text="End")
        sub.prop(sp,"model_set_id"); sub.prop(sp,"probability"); sub.prop(sp,"radius"); sub.prop(sp,"position")
    layout.separator(factor=0.2)
    box_cg = layout.box(); box_cg.label(text="Chaining Graph", icon="NODETREE")
    sub_cn = box_cg.box(); sub_cn.label(text=f"Nodes ({props.stat_nodes})")
    row_cn = sub_cn.row()
    row_cn.template_list("GTA5_UL_YMT_ChainingNodes","",props,"chaining_nodes",props,"chain_node_index",rows=3)
    col_cn = row_cn.column(align=True); col_cn.operator("gta5_ymt.add_chaining_node", text="",icon="ADD")
    ci = props.chain_node_index
    if 0 <= ci < len(props.chaining_nodes):
        cn = props.chaining_nodes[ci]; csub = sub_cn.box()
        csub.prop(cn,"scenario_type"); csub.prop(cn,"position")
        sub_cn.operator("gta5_ymt.remove_all_edges_node", text="🗑 Remove Edges", icon="TRASH")
    sub_ce = box_cg.box(); sub_ce.label(text=f"Edges ({props.stat_edges})")
    row_ce = sub_ce.row()
    row_ce.template_list("GTA5_UL_YMT_ChainingEdges","",props,"chaining_edges",props,"chain_edge_index",rows=3)
    col_ce = row_ce.column(align=True)
    col_ce.operator("gta5_ymt.add_chaining_edge",    text="",icon="ADD")
    col_ce.operator("gta5_ymt.remove_chaining_edge", text="",icon="REMOVE")
    ei = props.chain_edge_index
    if 0 <= ei < len(props.chaining_edges):
        ce = props.chaining_edges[ei]; esub = sub_ce.box()
        row_e = esub.row(align=True); row_e.prop(ce,"node_from",text="From"); row_e.prop(ce,"node_to",text="To")
        row_e2 = esub.row(align=True); row_e2.prop(ce,"action"); row_e2.prop(ce,"nav_mode"); row_e2.prop(ce,"nav_speed")


# ── TRAINS ────────────────────────────────────────────────────────────────────

def _draw_trains(layout, context, props):
    row = layout.row(align=True)
    row.operator("gta5_trains.import_dat", text="📂 Import .dat", icon="IMPORT")
    row.operator("gta5_trains.export_dat", text="💾 Export .dat", icon="EXPORT")
    box = layout.box(); box.label(text=f"Track : {props.track_name}", icon="CURVE_PATH")
    col = box.column(align=True)
    col.label(text=f"Points     : {props.stat_points}"); col.label(text=f"Junctions: {props.stat_junctions}")
    box2 = layout.box(); box2.label(text="Display", icon="HIDE_OFF")
    row = box2.row(align=True); row.prop(props,"show_track",toggle=True); row.prop(props,"show_junctions",toggle=True)
    layout.separator(factor=0.2)
    box3 = layout.box(); box3.label(text="Add Points", icon="ADD")
    row_t = box3.row(align=True)
    op_n = row_t.operator("gta5_trains.add_point", text="+ Normal", icon="ADD"); op_n.flag=0
    op_j = row_t.operator("gta5_trains.add_point", text="+ Junction", icon="DECORATE_DRIVER"); op_j.flag=4
    box3.operator("gta5_trains.mark_junction",       text="Toggle Selected Junction", icon="DECORATE_DRIVER")
    box3.operator("gta5_trains.sync_from_curve",     text="Sync from Curve", icon="FILE_REFRESH")
    box3.operator("gta5_trains.generate_from_curve", text="Generate from Active Curve", icon="CURVE_BEZCURVE")
    layout.separator(factor=0.2)
    box_pts = layout.box(); box_pts.label(text=f"Points ({props.stat_points})", icon="CURVE_PATH")
    row2 = box_pts.row()
    row2.template_list("GTA5_UL_TRAINS_Points","",props,"points",props,"point_index",rows=6)
    col = row2.column(align=True); col.operator("gta5_trains.remove_point", text="",icon="REMOVE")
    idx = props.point_index
    if 0 <= idx < len(props.points):
        pt = props.points[idx]; sub = box_pts.box(); sub.label(text=f"Point {idx}")
        sub.prop(pt,"position"); sub.prop(pt,"flag")
        sub.operator("gta5_trains.mark_junction", text="Toggle Junction", icon="DECORATE_DRIVER")


# ── AIDE ──────────────────────────────────────────────────────────────────────

class GTA5_PT_QuickHelp(Panel):
    bl_label       = "Quick Help"; bl_idname = "GTA5_PT_quick_help"
    bl_space_type  = "VIEW_3D"; bl_region_type = "UI"
    bl_category    = "GTA5 Paths"; bl_options = {"DEFAULT_CLOSED"}
    def draw(self, context):
        layout = self.layout; col = layout.column(); col.scale_y = 0.8
        col.label(text="── YND Viewport ──", icon="EMPTY_ARROWS")
        col.label(text="● Blue = vehicle node (CUBE)")
        col.label(text="● White = pedestrian node (SPHERE)")
        col.label(text="── Green = forward vehicle links")
        col.label(text="── Blue = back lanes links")
        col.label(text="── Red = pedestrian links")
        col.label(text="── Brown = freeway links")
        col.label(text="── Orange = dead-end links")
        col.label(text="□ Purple = junction bounds")
        col.label(text="↑ Yellow = direction ticks")
        col.separator()
        col.label(text="── YNV NavMesh ──", icon="MOD_FLUID")
        col.label(text="Edit Mode → select faces")
        col.label(text="→ Read flags / Apply preset")
        col.separator()
        col.label(text="── YMT Scenarios ──", icon="ARMATURE_DATA")
        col.label(text="Export → .ymt.xml (OpenIV/CodeWalker)")


_classes = [
    GTA5_UL_YNV_Portals, GTA5_UL_YNV_NavPoints,
    GTA5_UL_YND_Nodes, GTA5_UL_YND_Links,
    GTA5_UL_YMT_ScenarioPoints, GTA5_UL_YMT_ChainingNodes, GTA5_UL_YMT_ChainingEdges,
    GTA5_UL_TRAINS_Points,
    GTA5_PT_PathingEditor, GTA5_PT_QuickHelp,
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
