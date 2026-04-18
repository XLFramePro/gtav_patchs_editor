"""
ui.py — N-Panel for GTA V Pathing Editor
English UI, Sollumz-inspired layout.
"""
import bpy
from bpy.types import Panel, UIList
from .props import PED_SPECIAL_TYPES, ITYPE_NAMES

# ── UILists ───────────────────────────────────────────────────────────────────

class UL_YNV_Portals(UIList):
    bl_idname = "GTA5PE_UL_ynv_portals"
    def draw_item(self, ctx, layout, data, item, icon, ad, ap, index):
        row = layout.row(align=True)
        row.label(text=f"[T{item.portal_type}]", icon="LINKED")
        row.label(text=f"Poly {item.poly_from} → {item.poly_to}")

class UL_YNV_NavPoints(UIList):
    bl_idname = "GTA5PE_UL_ynv_navpoints"
    def draw_item(self, ctx, layout, data, item, icon, ad, ap, index):
        p = item.position
        layout.label(
            text=f"[T{item.point_type}]  ({p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f})",
            icon="EMPTY_SINGLE_ARROW")

class UL_YND_Nodes(UIList):
    bl_idname = "GTA5PE_UL_ynd_nodes"
    def draw_item(self, ctx, layout, data, item, icon, ad, ap, index):
        is_ped = item.nf1.special_type in PED_SPECIAL_TYPES
        row = layout.row(align=True)
        row.label(
            text=f"[{item.area_id}:{item.node_id}]  {item.street_name or '—'}",
            icon="USER" if is_ped else "AUTO")
        stype = item.nf1.special_type
        row.label(text=f"{len(item.links)}lk" +
                  (f"  {stype[:8]}" if stype != "NONE" else ""))

class UL_YND_Links(UIList):
    bl_idname = "GTA5PE_UL_ynd_links"
    def draw_item(self, ctx, layout, data, item, icon, ad, ap, index):
        dead = "  💀" if item.lf1.dead_end else ""
        sc   = "  SC" if item.lf2.shortcut else ""
        layout.label(
            text=f"→ [{item.to_area_id}:{item.to_node_id}]  "
                 f"L={item.link_length}  "
                 f"F{item.lf2.forward_lanes}/B{item.lf2.back_lanes}{dead}{sc}",
            icon="LINKED")

class UL_YMT_Points(UIList):
    bl_idname = "GTA5PE_UL_ymt_points"
    def draw_item(self, ctx, layout, data, item, icon, ad, ap, index):
        name = ITYPE_NAMES.get(item.itype, f"t{item.itype}")
        layout.label(
            text=f"[{item.itype}:{name}]  ({item.position[0]:.0f}, {item.position[1]:.0f})",
            icon="EMPTY_SINGLE_ARROW")

class UL_YMT_CNodes(UIList):
    bl_idname = "GTA5PE_UL_ymt_cnodes"
    def draw_item(self, ctx, layout, data, item, icon, ad, ap, index):
        layout.label(text=f"[{index}]  {item.scenario_type}",
                     icon="TRIA_RIGHT" if item.has_outgoing else "DOT")

class UL_YMT_CEdges(UIList):
    bl_idname = "GTA5PE_UL_ymt_cedges"
    def draw_item(self, ctx, layout, data, item, icon, ad, ap, index):
        layout.label(
            text=f"{item.node_from} → {item.node_to}  "
                 f"a={item.action} m={item.nav_mode} s={item.nav_speed}",
            icon="CURVE_PATH")

class UL_TRAINS_Points(UIList):
    bl_idname = "GTA5PE_UL_trains_points"
    def draw_item(self, ctx, layout, data, item, icon, ad, ap, index):
        ic  = "DECORATE_DRIVER" if item.flag == 4 else "CURVE_PATH"
        jct = "  [SWITCH]" if item.flag == 4 else ""
        layout.label(
            text=f"{index:4d}  ({item.position[0]:.2f}, "
                 f"{item.position[1]:.2f}, {item.position[2]:.2f}){jct}",
            icon=ic)


# ── Main Panel ────────────────────────────────────────────────────────────────

class GTA5PE_PT_Main(Panel):
    bl_label       = "GTA V Pathing Editor"
    bl_idname      = "GTA5PE_PT_main"
    bl_space_type  = "VIEW_3D"
    bl_region_type = "UI"
    bl_category    = "GTA5 PE"

    def draw(self, ctx):
        L  = self.layout
        gp = ctx.scene.gta5pe

        # Tab row
        row = L.row(align=True)
        row.prop_enum(gp, "tab", "YNV",    text="NavMesh")
        row.prop_enum(gp, "tab", "YND",    text="PathNodes")
        row.prop_enum(gp, "tab", "TRAINS", text="Trains")
        row.prop_enum(gp, "tab", "YMT",    text="Scenario")

        L.separator()

        if   gp.tab == "YNV":    _draw_ynv(L, ctx)
        elif gp.tab == "YND":    _draw_ynd(L, ctx)
        elif gp.tab == "TRAINS": _draw_trains(L, ctx)
        elif gp.tab == "YMT":    _draw_ymt(L, ctx)


# ── YNV Panel ─────────────────────────────────────────────────────────────────

def _draw_ynv(L, ctx):
    p = ctx.scene.gta5pe.ynv

    # Header note
    note = L.box()
    note.label(text="💡 Set Viewport Shading: Solid → Material Color", icon="INFO")

    # I/O
    box = L.box()
    box.label(text="NavMesh", icon="MOD_FLUID")
    row = box.row(align=True)
    row.operator("gta5pe.ynv_import", text="Import .ynv.xml", icon="IMPORT")
    row.operator("gta5pe.ynv_new",    text="New",             icon="FILE_NEW")
    box.operator("gta5pe.ynv_export", text="Export .ynv.xml", icon="EXPORT")
    if p.filepath:
        box.label(text=p.filepath, icon="FILE")

    # Stats
    sbox = L.box()
    col  = sbox.column(align=True)
    col.label(text=f"Area ID : {p.area_id}")
    col.label(text=f"Polygons: {p.stat_polys}   Portals: {len(p.portals)}")
    col.label(text=f"Nav Points: {len(p.nav_points)}   Materials: {p.stat_mats}")
    col.label(text=f"Content: {p.content_flags[:40] if p.content_flags else '—'}")

    # Bounding box
    bbox = L.box()
    bbox.label(text="Bounding Box", icon="CUBE")
    col = bbox.column(align=True)
    row = col.row(align=True)
    row.prop(p, "bb_min", text="Min")
    row2 = col.row(align=True)
    row2.prop(p, "bb_max", text="Max")
    bbox.prop(p, "show_bb", text="Show BB Overlay", toggle=True, icon="HIDE_OFF")
    row3 = bbox.row(align=True)
    row3.operator("gta5pe.ynv_compute_bb",      text="From Mesh",  icon="CUBE")
    row3.operator("gta5pe.ynv_compute_bb_grid", text="From Grid",  icon="GRID")

    # Polygon flags editor
    fbox = L.box()
    fbox.label(text="Polygon Flags", icon="FACE_MAPS")
    pf = p.edit_flags

    row_pre = fbox.row(align=True)
    row_pre.prop(p, "flag_preset", text="")
    row_pre.operator("gta5pe.ynv_apply_preset",  text="Apply Preset", icon="CHECKMARK")
    fbox.operator("gta5pe.ynv_apply_custom",     text="Apply Custom Flags", icon="FILE_TICK")

    row_util = fbox.row(align=True)
    row_util.operator("gta5pe.ynv_read_flags",     text="Read Active",    icon="EYEDROPPER")
    row_util.operator("gta5pe.ynv_refresh_colors", text="Refresh Colors", icon="MATERIAL")
    row_sel = fbox.row(align=True)
    row_sel.operator("gta5pe.ynv_select_similar",     text="Select Similar",   icon="RESTRICT_SELECT_OFF")
    row_sel.operator("gta5pe.ynv_update_auto_flags",  text="Auto Small/Large", icon="FILE_REFRESH")
    fbox.label(text="Flags auto-read on face select (Edit Mode)", icon="INFO")
    fbox.operator("gta5pe.ynv_add_polygon", text="Add Polygon at Cursor", icon="ADD")

    # Byte 0
    b0 = fbox.box(); b0.label(text="Byte 0 — Surface")
    g0 = b0.grid_flow(columns=2, align=True, even_columns=True)
    for attr in ("is_small","is_large","is_pavement","is_in_shelter",
                 "unused_b0_4","unused_b0_5","is_too_steep","is_water"):
        g0.prop(pf, attr)

    # Byte 1
    b1 = fbox.box(); b1.label(text="Byte 1 — Audio / Properties")
    g1 = b1.grid_flow(columns=2, align=True, even_columns=True)
    for attr in ("audio_reverb_size","audio_reverb_wet","unused_b1_4",
                 "is_near_car_node","is_interior","is_isolated"):
        g1.prop(pf, attr)

    # Byte 2
    b2 = fbox.box(); b2.label(text="Byte 2 — Behaviour")
    g2 = b2.grid_flow(columns=2, align=True, even_columns=True)
    for attr in ("is_network_spawn","is_road","lies_along_edge",
                 "is_train_track","is_shallow_water","ped_density"):
        g2.prop(pf, attr)

    # Byte 3 – Cover
    b3 = fbox.box(); b3.label(text="Byte 3 — Cover Directions")
    g3 = b3.grid_flow(columns=4, align=True, even_columns=True)
    for attr in ("cover_dir0","cover_dir1","cover_dir2","cover_dir3",
                 "cover_dir4","cover_dir5","cover_dir6","cover_dir7"):
        g3.prop(pf, attr)

    fbox.prop(pf, "is_dlc_stitch")

    # Portals (links)
    pbox = L.box()
    row = pbox.row(align=True)
    row.label(text=f"Portals ({len(p.portals)})", icon="LINKED")
    row.prop(p, "show_portals", icon="HIDE_OFF", text="", toggle=True)
    if getattr(p, "show_portals", False):
        pbox.template_list("GTA5PE_UL_ynv_portals", "", p, "portals", p, "portal_idx")
        row2 = pbox.row(align=True)
        row2.operator("gta5pe.ynv_add_portal", text="Add",    icon="ADD")
        row2.operator("gta5pe.ynv_rem_portal", text="Remove", icon="REMOVE")
        if 0 <= p.portal_idx < len(p.portals):
            pt = p.portals[p.portal_idx]
            b  = pbox.box()
            b.label(text=f"Portal {p.portal_idx}", icon="LINKED")
            b.prop(pt, "portal_type"); b.prop(pt, "angle")
            b.prop(pt, "poly_from");   b.prop(pt, "poly_to")
            b.prop(pt, "pos_from");    b.prop(pt, "pos_to")

    # Cover Points
    cpbox = L.box()
    row = cpbox.row(align=True)
    row.label(text=f"Cover Points ({len(p.nav_points)})", icon="EMPTY_SINGLE_ARROW")
    row.prop(p, "show_navpts", icon="HIDE_OFF", text="", toggle=True)
    if getattr(p, "show_navpts", False):
        cpbox.template_list("GTA5PE_UL_ynv_navpoints", "", p, "nav_points", p, "navpt_idx")
        row2 = cpbox.row(align=True)
        row2.operator("gta5pe.ynv_add_navpt", text="Add",    icon="ADD")
        row2.operator("gta5pe.ynv_rem_navpt", text="Remove", icon="REMOVE")
    cpbox.operator("gta5pe.ynv_sync", text="Sync Empties → Props", icon="FILE_REFRESH")


# ── YND Panel ─────────────────────────────────────────────────────────────────

def _draw_ynd(L, ctx):
    p = ctx.scene.gta5pe.ynd

    # I/O
    box = L.box()
    box.label(text="Path Nodes", icon="AUTO")
    row = box.row(align=True)
    row.operator("gta5pe.ynd_import", text="Import .ynd.xml", icon="IMPORT")
    row.operator("gta5pe.ynd_new",    text="New",             icon="FILE_NEW")
    box.operator("gta5pe.ynd_export", text="Export .ynd.xml", icon="EXPORT")
    if p.filepath:
        box.label(text=p.filepath, icon="FILE")

    # Stats
    sbox = L.box()
    col  = sbox.column(align=True)
    col.label(text=f"Area ID  : {p.area_id}")
    col.label(text=f"Total    : {p.stat_total}  nodes")
    col.label(text=f"Vehicle  : {p.stat_vehicle}   Ped: {p.stat_ped}")
    col.label(text=f"Junctions: {p.stat_jct}")

    # Sync (before export if moved)
    srow = L.row(align=True)
    srow.operator("gta5pe.ynd_sync", text="Sync Positions", icon="FILE_REFRESH")
    srow.label(text="(run before export if nodes moved)", icon="INFO")

    # Viewport toggles
    vbox = L.box()
    vbox.label(text="Overlay", icon="OVERLAY")
    row = vbox.row(align=True)
    row.prop(p, "show_vehicle",   text="Vehicle", toggle=True, icon="AUTO")
    row.prop(p, "show_ped",       text="Ped",     toggle=True, icon="USER")
    row.prop(p, "show_links",     text="Links",   toggle=True, icon="LINKED")
    row.prop(p, "show_junctions", text="Jct",     toggle=True, icon="CUBE")

    # Add nodes
    abox = L.box()
    abox.label(text="Add Node", icon="ADD")
    row2 = abox.row(align=True)
    row2.operator("gta5pe.ynd_add_veh", text="Vehicle", icon="AUTO")
    row2.operator("gta5pe.ynd_add_ped", text="Ped",     icon="USER")
    abox.prop(p, "area_id", text="Area ID")

    # Node list
    nbox = L.box()
    nbox.label(text=f"Nodes ({p.stat_total})", icon="MESH_DATA")
    nbox.template_list("GTA5PE_UL_ynd_nodes", "", p, "nodes", p, "node_idx",
                       rows=5, maxrows=8)

    # Active node details
    if 0 <= p.node_idx < len(p.nodes):
        nd   = p.nodes[p.node_idx]
        dbox = L.box()
        dbox.label(text=f"Node [{nd.area_id}:{nd.node_id}]  {nd.street_name or ''}",
                   icon="PROPERTIES")

        col = dbox.column(align=True)
        col.prop(nd, "area_id");   col.prop(nd, "node_id")
        col.prop(nd, "street_name")
        col.prop(nd, "position")
        dbox.operator("gta5pe.ynd_rem_node", text="Delete Node", icon="TRASH")

        # Flags in a 2-col grid
        fbx = dbox.box(); fbx.label(text="Node Flags")
        g = fbx.grid_flow(columns=2, align=True, even_columns=True)
        g.prop(nd.nf0, "scripted")
        g.prop(nd.nf0, "gps_enabled")
        g.prop(nd.nf0, "offroad")
        g.prop(nd.nf0, "no_big_vehicles")
        g.prop(nd.nf0, "cannot_go_right")
        g.prop(nd.nf0, "cannot_go_left")
        fbx.prop(nd.nf1, "special_type")
        fbx.prop(nd.nf1, "slip_lane")
        fbx.prop(nd.nf1, "indicate_keep_left")
        fbx.prop(nd.nf1, "indicate_keep_right")
        g2 = fbx.grid_flow(columns=2, align=True, even_columns=True)
        g2.prop(nd.nf2, "no_gps")
        g2.prop(nd.nf2, "junction")
        g2.prop(nd.nf2, "freeway")
        g2.prop(nd.nf2, "water_boats")
        g2.prop(nd.nf2, "disabled_1")
        g2.prop(nd.nf2, "disabled_2")
        fbx.prop(nd.nf3, "tunnel")
        fbx.prop(nd.nf3, "heuristic")
        fbx.prop(nd.nf4, "density")
        fbx.prop(nd.nf4, "deadendness")
        fbx.prop(nd.nf5, "speed")
        fbx.prop(nd.nf5, "has_junction_heightmap")

        # Links
        lbx = dbox.box()
        lbx.label(text=f"Links ({len(nd.links)})", icon="LINKED")
        lbx.template_list("GTA5PE_UL_ynd_links", "", nd, "links", nd, "link_idx",
                          rows=3, maxrows=5)
        row3 = lbx.row(align=True)
        row3.operator("gta5pe.ynd_add_link",     text="Add",        icon="ADD")
        row3.operator("gta5pe.ynd_rem_link",     text="Remove",     icon="REMOVE")
        row3.operator("gta5pe.ynd_rem_all_links",text="Clear All",  icon="X")
        lbx.operator("gta5pe.ynd_link_to",       text="Link To...", icon="ARROW_LEFTRIGHT")

        # Active link flags
        if 0 <= nd.link_idx < len(nd.links):
            lk   = nd.links[nd.link_idx]
            lfbx = dbox.box()
            lfbx.label(text=f"Link → [{lk.to_area_id}:{lk.to_node_id}]")
            lfbx.prop(lk, "to_area_id"); lfbx.prop(lk, "to_node_id")
            lfbx.prop(lk, "link_length")
            lfbx.prop(lk.lf0, "gps_both_ways")
            lfbx.prop(lk.lf0, "block_if_no_lanes")
            g3 = lfbx.grid_flow(columns=2, align=True, even_columns=True)
            g3.prop(lk.lf1, "dead_end"); g3.prop(lk.lf1, "narrow_road")
            g3.prop(lk.lf1, "dead_end_exit"); g3.prop(lk.lf1, "negative_offset")
            lfbx.prop(lk.lf2, "forward_lanes")
            lfbx.prop(lk.lf2, "back_lanes")
            lfbx.prop(lk.lf2, "shortcut")
            lfbx.prop(lk.lf2, "dont_use_for_navigation")


# ── TRAINS Panel ──────────────────────────────────────────────────────────────

def _draw_trains(L, ctx):
    p = ctx.scene.gta5pe.trains

    box = L.box()
    box.label(text="Train Tracks", icon="CURVE_PATH")
    row = box.row(align=True)
    row.operator("gta5pe.trains_import", text="Import .dat", icon="IMPORT")
    row.operator("gta5pe.trains_new",    text="New",         icon="FILE_NEW")
    box.operator("gta5pe.trains_export", text="Export .dat", icon="EXPORT")
    if p.filepath:
        box.label(text=p.filepath, icon="FILE")

    box.label(text=f"Points: {len(p.points)}  "
                   f"Switches: {sum(1 for pt in p.points if pt.flag==4)}")

    # Overlay
    ovbox = L.box()
    ovbox.label(text="Overlay", icon="OVERLAY")
    row2 = ovbox.row(align=True)
    row2.prop(p, "show_track", text="Track",    toggle=True, icon="CURVE_PATH")
    row2.prop(p, "show_jct",   text="Switches", toggle=True, icon="NODE")

    # Add
    abox = L.box()
    abox.label(text="Add Point", icon="ADD")
    row3 = abox.row(align=True)
    row3.operator("gta5pe.trains_add_normal",   text="Normal",  icon="CURVE_PATH")
    row3.operator("gta5pe.trains_add_junction", text="Switch",  icon="DECORATE_DRIVER")

    # List
    lbox = L.box()
    lbox.label(text=f"Points ({len(p.points)})", icon="MESH_DATA")
    lbox.template_list("GTA5PE_UL_trains_points", "", p, "points", p, "point_idx",
                       rows=5, maxrows=8)
    if 0 <= p.point_idx < len(p.points):
        pt  = p.points[p.point_idx]
        ebx = lbox.box()
        ebx.label(text=f"Point {p.point_idx}  Flag: {pt.flag}", icon="PROPERTIES")
        ebx.prop(pt, "position")
        # Flag picker
        fbx2 = ebx.box(); fbx2.label(text="Set Flag", icon="SETTINGS")
        row5 = fbx2.row(align=True)
        op0 = row5.operator("gta5pe.trains_set_flag", text="Normal(0)")
        op0.flag = 0
        op1 = row5.operator("gta5pe.trains_set_flag", text="Boost(1)")
        op1.flag = 1
        row6 = fbx2.row(align=True)
        op4 = row6.operator("gta5pe.trains_set_flag", text="Switch(4)")
        op4.flag = 4
        op5 = row6.operator("gta5pe.trains_set_flag", text="Boost+Switch(5)")
        op5.flag = 5
        row4 = ebx.row(align=True)
        row4.operator("gta5pe.trains_toggle_junction", text="Toggle Switch", icon="NODE")
        row4.operator("gta5pe.trains_remove_point",    text="Delete",        icon="TRASH")

    # Tools
    tbx = L.box()
    tbx.label(text="Tools", icon="TOOL_SETTINGS")
    tbx.operator("gta5pe.trains_sync_curve",     text="Sync Positions from Objects", icon="FILE_REFRESH")
    tbx.operator("gta5pe.trains_gen_from_curve", text="Generate from Active Curve",  icon="CURVE_BEZCURVE")

    # Flags reference
    fbx = L.box()
    fbx.label(text="Available Flags", icon="INFO")
    col = fbx.column(align=True)
    col.label(text="0 = Normal point",       icon="CURVE_PATH")
    col.label(text="1 = Boost (faster)",     icon="DECORATE_DRIVER")
    col.label(text="4 = Switch/Junction",    icon="NODE")
    col.label(text="5 = Boost + Switch",     icon="NODE")


# ── YMT Panel ─────────────────────────────────────────────────────────────────

def _draw_ymt(L, ctx):
    p = ctx.scene.gta5pe.ymt

    box = L.box()
    box.label(text="Scenario Points (.ymt)", icon="SCENE_DATA")
    row = box.row(align=True)
    row.operator("gta5pe.ymt_import", text="Import .ymt.xml", icon="IMPORT")
    row.operator("gta5pe.ymt_new",    text="New",             icon="FILE_NEW")
    box.operator("gta5pe.ymt_export", text="Export .ymt.xml", icon="EXPORT")
    if p.filepath:
        box.label(text=p.filepath, icon="FILE")
    box.label(text=f"Version: {p.version_number}   Points: {len(p.points)}")

    # Point list
    pbox = L.box()
    pbox.label(text=f"Scenario Points ({len(p.points)})", icon="EMPTY_SINGLE_ARROW")
    pbox.template_list("GTA5PE_UL_ymt_points", "", p, "points", p, "point_idx",
                       rows=5, maxrows=8)
    row2 = pbox.row(align=True)
    row2.operator("gta5pe.ymt_add_pt", text="Add",    icon="ADD")
    row2.operator("gta5pe.ymt_rem_pt", text="Remove", icon="REMOVE")

    if 0 <= p.point_idx < len(p.points):
        pt  = p.points[p.point_idx]
        ebx = L.box()
        ebx.label(text=f"Point {p.point_idx}", icon="PROPERTIES")
        ebx.prop(pt, "itype")
        ebx.prop(pt, "position")
        g = ebx.grid_flow(columns=2, align=True, even_columns=True)
        g.prop(pt, "time_start"); g.prop(pt, "time_end")
        g.prop(pt, "probability"); g.prop(pt, "avail_mp_sp")
        g.prop(pt, "radius"); g.prop(pt, "time_till_leaves")
        ebx.prop(pt, "flags")
        # Flags picker
        from .props import SCENARIO_FLAGS
        fpick = ebx.box(); fpick.label(text="Quick Flags", icon="SETTINGS")
        grid_f = fpick.grid_flow(columns=2, align=True, even_columns=True)
        for flag_name in SCENARIO_FLAGS:
            op = grid_f.operator("gta5pe.ymt_toggle_flag", text=flag_name[:18])
            op.flag_name = flag_name

    # Chaining graph
    cbx = L.box()
    row3 = cbx.row(align=True)
    row3.label(text=f"Chain Nodes ({len(p.chain_nodes)})", icon="NODETREE")
    row3.prop(p, "show_chain", text="", icon="HIDE_OFF", toggle=True)
    cbx.template_list("GTA5PE_UL_ymt_cnodes", "", p, "chain_nodes", p, "cnode_idx",
                      rows=3, maxrows=5)
    cbx.operator("gta5pe.ymt_add_cn", text="Add Chain Node", icon="ADD")

    ebox = L.box()
    ebox.label(text=f"Chain Edges ({len(p.chain_edges)})", icon="CURVE_PATH")
    ebox.template_list("GTA5PE_UL_ymt_cedges", "", p, "chain_edges", p, "cedge_idx",
                       rows=3, maxrows=5)
    row4 = ebox.row(align=True)
    row4.operator("gta5pe.ymt_add_ce", text="Add Edge",       icon="ADD")
    row4.operator("gta5pe.ymt_rem_ce", text="Remove Edge",    icon="REMOVE")
    ebox.operator("gta5pe.ymt_sync",   text="Sync → Scene",   icon="FILE_REFRESH")


# ── Registration ──────────────────────────────────────────────────────────────

_CLASSES = [
    UL_YNV_Portals, UL_YNV_NavPoints,
    UL_YND_Nodes, UL_YND_Links,
    UL_YMT_Points, UL_YMT_CNodes, UL_YMT_CEdges,
    UL_TRAINS_Points,
    GTA5PE_PT_Main,
]

def register():
    for cls in _CLASSES:
        try:   bpy.utils.unregister_class(cls)
        except Exception: pass
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_CLASSES):
        try:   bpy.utils.unregister_class(cls)
        except Exception: pass
