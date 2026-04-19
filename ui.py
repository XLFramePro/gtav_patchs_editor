"""
ui.py — N-Panel GTA V Pathing Editor with complete YND panel
(flags structured NodeFlags0-5, LinkFlags0-2, reference design ynd.rar).
"""
import bpy
from bpy.types import Panel, UIList
from .operators_ynv import _read_selected_face_flags


def update_ynv_flags():
    """Timer function to auto-update YNV selected face flags."""
    try:
        if bpy.context.scene.gta5_pathing.active_module == "YNV":
            props = bpy.context.scene.gta5_pathing.ynv
            if (bpy.context.active_object and
                bpy.context.active_object.get("ynv_type") == "poly_mesh" and
                bpy.context.active_object.mode == "EDIT"):
                _read_selected_face_flags(bpy.context, props)
    except Exception:
        pass  # Ignore errors in timer
    return 0.2  # Run every 0.2 seconds


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
        dead = " [dead]" if item.flags1.dead_end else ""
        gps  = " [GPS]"  if item.flags0.gps_both_ways else ""
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


# ── MAIN PANEL ──────────────────────────────────────────────────────────────

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
    # Import/Export
    box = layout.box()
    box.label(text="Import / Export", icon="FILE_FOLDER")
    row = box.row(align=True)
    row.operator("gta5_ynv.import_xml", text="Import YNV", icon="IMPORT")
    row.operator("gta5_ynv.export_xml", text="Export YNV", icon="EXPORT")

    # Stats
    box = layout.box()
    box.label(text="NavMesh Info", icon="INFO")
    col = box.column(align=True)
    col.label(text=f"Area ID: {props.area_id}")
    col.label(text=f"Polygons: {props.stat_polygons}")
    col.label(text=f"Portals: {props.stat_portals}")
    col.label(text=f"Nav Points: {props.stat_navpoints}")

    # Bounding Box
    box = layout.box()
    box.label(text="Bounding Box", icon="CUBE")
    col = box.column(align=True)
    col.prop(props, "bb_min", text="Min")
    col.prop(props, "bb_max", text="Max")
    box.operator("gta5_ynv.compute_bbox", text="Compute BB", icon="MODIFIER")

    # Display Options
    box = layout.box()
    box.label(text="Display", icon="HIDE_OFF")
    col = box.column(align=True)
    col.prop(props, "show_polygons", text="Polygons")
    col.prop(props, "show_portals", text="Portals")
    col.prop(props, "show_navpoints", text="Nav Points")

    # Polygon Flags Editor
    box = layout.box()
    box.label(text="Polygon Flags", icon="TOOL_SETTINGS")
    row = box.row(align=True)
    row.prop(props, "flag_preset", text="")
    row.operator("gta5_ynv.apply_flags_preset", text="Apply Preset", icon="CHECKMARK")
    row.operator("gta5_ynv.add_polygon", text="Add Polygon", icon="ADD")

    # Custom Flags
    sub = box.box()
    sub.label(text="Custom Flags (Edit Mode)", icon="EDITMODE_HLT")
    row = sub.row(align=True)
    row.operator("gta5_ynv.read_selected_flags", text="Read Selection", icon="EYEDROPPER")
    row.operator("gta5_ynv.apply_custom_flags", text="Apply Custom", icon="CHECKMARK")

    pf = props.selected_poly_flags
    # Flags sections
    flags_box = sub.box()
    flags_box.label(text="Surface (Byte 0)", icon="MESH_DATA")
    grid = flags_box.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
    for attr in ["small_poly", "large_poly", "is_pavement", "is_underground", "unused_f1_4", "unused_f1_5", "is_too_steep", "is_water"]:
        grid.prop(pf, attr)

    flags_box = sub.box()
    flags_box.label(text="Audio/Props (Byte 1)", icon="SPEAKER")
    grid = flags_box.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
    for attr in ["audio_prop1", "audio_prop2", "audio_prop3", "unused_f2_3", "near_car_node", "is_interior", "is_isolated", "unused_f2_7"]:
        grid.prop(pf, attr)

    flags_box = sub.box()
    flags_box.label(text="Behavior (Byte 2)", icon="PHYSICS")
    grid = flags_box.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
    for attr in ["can_spawn", "is_road", "along_edge", "is_train_track", "is_shallow", "ped_density1", "ped_density2", "ped_density3"]:
        grid.prop(pf, attr)

    flags_box = sub.box()
    flags_box.label(text="Cover (Byte 3)", icon="MOD_BUILD")
    grid = flags_box.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
    for attr in ["cover_south", "cover_south2", "cover_east", "cover_north", "cover_north2", "cover_north3", "cover_west", "cover_south3"]:
        grid.prop(pf, attr)

    flags_box = sub.box()
    flags_box.label(text="Internal (Bytes 4-5)", icon="SETTINGS")
    row = flags_box.row(align=True)
    row.prop(pf, "byte4")
    row.prop(pf, "byte5")

    # Mesh Cutter (placeholder)
    box = layout.box()
    box.label(text="Mesh Tools", icon="MOD_DECIM")
    col = box.column(align=True)
    col.prop(props, "tile_size")
    col.prop(props, "offset_x")
    col.prop(props, "offset_y")
    box.operator("gta5_ynv.split_mesh", text="Split Mesh", icon="MOD_EXPLODE")

    # Portals
    box = layout.box()
    box.label(text=f"Portals ({props.stat_portals})", icon="OBJECT_DATA")
    row = box.row()
    row.template_list("GTA5_UL_YNV_Portals", "", props, "portals", props, "portal_index", rows=3)
    col = row.column(align=True)
    col.operator("gta5_ynv.add_portal", text="", icon="ADD")
    col.operator("gta5_ynv.remove_portal", text="", icon="REMOVE")
    if 0 <= props.portal_index < len(props.portals):
        p = props.portals[props.portal_index]
        sub = box.box()
        sub.label(text=f"Portal {props.portal_index}")
        sub.prop(p, "portal_type")
        sub.prop(p, "angle")
        sub.prop(p, "poly_from")
        sub.prop(p, "poly_to")
        sub.prop(p, "pos_from")
        sub.prop(p, "pos_to")

    # Nav Points
    box = layout.box()
    box.label(text=f"Nav Points ({props.stat_navpoints})", icon="EMPTY_SINGLE_ARROW")
    row = box.row()
    row.template_list("GTA5_UL_YNV_NavPoints", "", props, "nav_points", props, "nav_point_index", rows=3)
    col = row.column(align=True)
    col.operator("gta5_ynv.add_nav_point", text="", icon="ADD")
    col.operator("gta5_ynv.remove_nav_point", text="", icon="REMOVE")
    if 0 <= props.nav_point_index < len(props.nav_points):
        np = props.nav_points[props.nav_point_index]
        sub = box.box()
        sub.label(text=f"Nav Point {props.nav_point_index}")
        sub.prop(np, "point_type")
        sub.prop(np, "angle")
        sub.prop(np, "position")
    box.operator("gta5_ynv.sync_from_objects", text="Sync from Objects", icon="FILE_REFRESH")


# ── YND ──────────────────────────────────────────────────────────────────────

def _draw_ynd(layout, context, props):
    # Import/Export
    box = layout.box()
    box.label(text="Import / Export", icon="FILE_FOLDER")
    row = box.row(align=True)
    row.operator("gta5_ynd.import_xml", text="Import YND", icon="IMPORT")
    row.operator("gta5_ynd.export_xml", text="Export YND", icon="EXPORT")

    # Click-select
    box = layout.box()
    box.label(text="Selection", icon="CURSOR")
    box.operator("gta5_ynd.activate_click_select", text="Activate Node Click-Select", icon="CURSOR")

    # Stats
    box = layout.box()
    box.label(text="PathNodes Info", icon="INFO")
    col = box.column(align=True)
    col.label(text=f"Area ID: {props.area_id}")
    col.label(text=f"Total Nodes: {props.stat_nodes}")
    col.label(text=f"Vehicles: {props.stat_vehicle}")
    col.label(text=f"Pedestrians: {props.stat_ped}")
    col.label(text=f"Junctions: {props.stat_junctions}")

    # Display
    box = layout.box()
    box.label(text="Display", icon="HIDE_OFF")
    col = box.column(align=True)
    col.prop(props, "show_vehicle", text="Vehicles")
    col.prop(props, "show_ped", text="Pedestrians")
    col.prop(props, "show_links", text="Links")
    col.prop(props, "show_junctions", text="Junctions")
    box.prop(props, "filter_street")
    row = box.row(align=True)
    row.operator("gta5_ynd.sync_from_objects", text="Sync from Objects", icon="FILE_REFRESH")
    row.operator("gta5_ynd.repair_local_ids", text="Repair Local IDs", icon="TOOL_SETTINGS")

    # Nodes
    box = layout.box()
    box.label(text="Nodes", icon="EMPTY_ARROWS")
    row = box.row(align=True)
    row.operator("gta5_ynd.add_vehicle_node", text="Add Vehicle", icon="AUTO")
    row.operator("gta5_ynd.add_ped_node", text="Add Pedestrian", icon="USER")

    row = box.row()
    row.template_list("GTA5_UL_YND_Nodes", "", props, "nodes", props, "node_index", rows=6)
    col = row.column(align=True)
    col.operator("gta5_ynd.remove_node", text="", icon="REMOVE")

    if 0 <= props.node_index < len(props.nodes):
        node = props.nodes[props.node_index]
        from .properties import PED_SPECIAL_TYPES
        is_ped = node.flags1.special_type in PED_SPECIAL_TYPES

        sub = box.box()
        sub.label(text=f"{'Pedestrian' if is_ped else 'Vehicle'} — {node.area_id}:{node.node_id}")
        row = sub.row(align=True)
        row.prop(node, "area_id")
        row.prop(node, "node_id")
        sub.prop(node, "street_name")
        sub.prop(node, "position")

        # Flags
        sub2 = sub.box()
        sub2.label(text="Node Flags", icon="BOOKMARKS")

        # Special Type
        flags_box = sub2.box()
        flags_box.label(text="Special Type", icon="SETTINGS")
        flags_box.prop(node.flags1, "special_type")
        grid = flags_box.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
        grid.prop(node.flags1, "slip_lane")
        grid.prop(node.flags1, "indicate_keep_left")
        grid.prop(node.flags1, "indicate_keep_right")

        # Navigation
        flags_box = sub2.box()
        flags_box.label(text="Navigation", icon="CURVE_PATH")
        grid = flags_box.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
        for attr in ["scripted", "gps_enabled", "unused_4", "offroad", "unused_16", "no_big_vehicles", "cannot_go_right", "cannot_go_left"]:
            grid.prop(node.flags0, attr)

        # Zone
        flags_box = sub2.box()
        flags_box.label(text="Zone", icon="WORLD")
        grid = flags_box.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
        for attr in ["no_gps", "unused_2", "junction", "unused_8", "disabled_1", "water_boats", "freeway", "disabled_2"]:
            grid.prop(node.flags2, attr)

        # Additional
        flags_box = sub2.box()
        flags_box.label(text="Additional", icon="MODIFIER")
        row = flags_box.row(align=True)
        row.prop(node.flags3, "tunnel")
        row.prop(node.flags3, "heuristic")
        row = flags_box.row(align=True)
        row.prop(node.flags4, "density")
        row.prop(node.flags4, "deadendness")
        row.prop(node.flags4, "left_turn_only")
        row = flags_box.row(align=True)
        row.prop(node.flags5, "speed")
        row.prop(node.flags5, "has_junction_heightmap")

        # Junction
        if node.flags2.junction and node.flags5.has_junction_heightmap:
            jct_box = sub2.box()
            jct_box.label(text="Junction", icon="GRID")
            jct = node.junction
            row = jct_box.row(align=True)
            row.prop(jct, "min_z")
            row.prop(jct, "max_z")
            row = jct_box.row(align=True)
            row.prop(jct, "pos_x")
            row.prop(jct, "pos_y")
            row = jct_box.row(align=True)
            row.prop(jct, "size_x")
            row.prop(jct, "size_y")
            jct_box.label(text="Use CodeWalker to generate heightmap", icon="ERROR")

        # Links
        sub3 = sub.box()
        sub3.label(text=f"Links ({len(node.links)})", icon="LINKED")
        row = sub3.row(align=True)
        row.operator("gta5_ynd.add_link", text="Add Link", icon="ADD")
        row.operator("gta5_ynd.link_two_nodes", text="Link to...", icon="LINKED")
        row.operator("gta5_ynd.remove_all_links", text="Remove All", icon="TRASH")

        row = sub3.row()
        row.template_list("GTA5_UL_YND_Links", "", node, "links", node, "link_index", rows=4)
        col = row.column(align=True)
        col.operator("gta5_ynd.remove_link", text="", icon="REMOVE")

        if 0 <= node.link_index < len(node.links):
            lk = node.links[node.link_index]
            lk_box = sub3.box()
            lk_box.label(text=f"Link {node.link_index} → {lk.to_area_id}:{lk.to_node_id}")
            row = lk_box.row(align=True)
            row.prop(lk, "to_area_id", text="Area")
            row.prop(lk, "to_node_id", text="Node")
            lk_box.label(text=f"Length: {lk.link_length}")

            # Link Flags
            flags_box = lk_box.box()
            flags_box.label(text="GPS", icon="VIEW_PAN")
            grid = flags_box.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
            grid.prop(lk.flags0, "gps_both_ways")
            grid.prop(lk.flags0, "block_if_no_lanes")
            grid.prop(lk.flags0, "unknown_1")
            grid.prop(lk.flags0, "unknown_2")

            flags_box = lk_box.box()
            flags_box.label(text="Route", icon="CURVE_BEZCURVE")
            grid = flags_box.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
            grid.prop(lk.flags1, "unused_1")
            grid.prop(lk.flags1, "narrow_road")
            grid.prop(lk.flags1, "dead_end")
            grid.prop(lk.flags1, "dead_end_exit")
            grid.prop(lk.flags1, "negative_offset")
            grid.prop(lk.flags1, "offset")

            flags_box = lk_box.box()
            flags_box.label(text="Lanes", icon="MOD_ARRAY")
            grid = flags_box.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
            grid.prop(lk.flags2, "dont_use_for_navigation")
            grid.prop(lk.flags2, "shortcut")
            grid.prop(lk.flags2, "back_lanes")
            grid.prop(lk.flags2, "forward_lanes")


# ── YMT ──────────────────────────────────────────────────────────────────────

def _draw_ymt(layout, context, props):
    # Import/Export
    box = layout.box()
    box.label(text="Import / Export", icon="FILE_FOLDER")
    row = box.row(align=True)
    row.operator("gta5_ymt.import_xml", text="Import YMT", icon="IMPORT")
    row.operator("gta5_ymt.export_xml", text="Export YMT", icon="EXPORT")

    # Stats
    box = layout.box()
    box.label(text="Scenarios Info", icon="INFO")
    col = box.column(align=True)
    col.label(text=f"Version: {props.version_number}")
    col.label(text=f"Points: {props.stat_points}")
    col.label(text=f"Nodes: {props.stat_nodes}")
    col.label(text=f"Edges: {props.stat_edges}")
    col.label(text=f"Chains: {props.stat_chains}")

    # Display
    box = layout.box()
    box.label(text="Display", icon="HIDE_OFF")
    col = box.column(align=True)
    col.prop(props, "show_scenario_pts", text="Scenario Points")
    col.prop(props, "show_chain_nodes", text="Chain Nodes")
    col.prop(props, "show_chain_edges", text="Chain Edges")
    box.operator("gta5_ymt.sync_from_objects", text="Sync from Objects", icon="FILE_REFRESH")

    # Scenario Points
    box = layout.box()
    box.label(text="Scenario Points", icon="EMPTY_SINGLE_ARROW")
    row = box.row()
    row.template_list("GTA5_UL_YMT_ScenarioPoints", "", props, "scenario_points", props, "point_index", rows=5)
    col = row.column(align=True)
    col.operator("gta5_ymt.add_scenario_point", text="", icon="ADD")
    col.operator("gta5_ymt.remove_scenario_point", text="", icon="REMOVE")
    if 0 <= props.point_index < len(props.scenario_points):
        sp = props.scenario_points[props.point_index]
        sub = box.box()
        sub.label(text=f"Point {props.point_index}")
        sub.prop(sp, "itype")
        sub.prop(sp, "flags")
        row = sub.row(align=True)
        row.prop(sp, "time_start", text="Start")
        row.prop(sp, "time_end", text="End")
        sub.prop(sp, "model_set_id")
        sub.prop(sp, "probability")
        sub.prop(sp, "radius")
        sub.prop(sp, "position")

    # Chaining Graph
    box = layout.box()
    box.label(text="Chaining Graph", icon="NODETREE")

    # Nodes
    sub = box.box()
    sub.label(text=f"Nodes ({props.stat_nodes})")
    row = sub.row()
    row.template_list("GTA5_UL_YMT_ChainingNodes", "", props, "chaining_nodes", props, "chain_node_index", rows=3)
    col = row.column(align=True)
    col.operator("gta5_ymt.add_chaining_node", text="", icon="ADD")
    if 0 <= props.chain_node_index < len(props.chaining_nodes):
        cn = props.chaining_nodes[props.chain_node_index]
        csub = sub.box()
        csub.prop(cn, "scenario_type")
        csub.prop(cn, "position")
        sub.operator("gta5_ymt.remove_all_edges_node", text="Remove Edges", icon="TRASH")

    # Edges
    sub = box.box()
    sub.label(text=f"Edges ({props.stat_edges})")
    row = sub.row()
    row.template_list("GTA5_UL_YMT_ChainingEdges", "", props, "chaining_edges", props, "chain_edge_index", rows=3)
    col = row.column(align=True)
    col.operator("gta5_ymt.add_chaining_edge", text="", icon="ADD")
    col.operator("gta5_ymt.remove_chaining_edge", text="", icon="REMOVE")
    if 0 <= props.chain_edge_index < len(props.chaining_edges):
        ce = props.chaining_edges[props.chain_edge_index]
        esub = sub.box()
        row = esub.row(align=True)
        row.prop(ce, "node_from", text="From")
        row.prop(ce, "node_to", text="To")
        row = esub.row(align=True)
        row.prop(ce, "action")
        row.prop(ce, "nav_mode")
        row.prop(ce, "nav_speed")


# ── TRAINS ────────────────────────────────────────────────────────────────────

def _draw_trains(layout, context, props):
    # Import/Export
    box = layout.box()
    box.label(text="Import / Export", icon="FILE_FOLDER")
    row = box.row(align=True)
    row.operator("gta5_trains.import_dat", text="Import DAT", icon="IMPORT")
    row.operator("gta5_trains.export_dat", text="Export DAT", icon="EXPORT")

    # Stats
    box = layout.box()
    box.label(text="Track Info", icon="INFO")
    col = box.column(align=True)
    col.label(text=f"Track: {props.track_name}")
    col.label(text=f"Points: {props.stat_points}")
    col.label(text=f"Junctions: {props.stat_junctions}")

    # Display
    box = layout.box()
    box.label(text="Display", icon="HIDE_OFF")
    col = box.column(align=True)
    col.prop(props, "show_track", text="Track")
    col.prop(props, "show_junctions", text="Junctions")

    # Add Points
    box = layout.box()
    box.label(text="Add Points", icon="ADD")
    row = box.row(align=True)
    op_n = row.operator("gta5_trains.add_point", text="Normal", icon="ADD")
    op_n.flag = 0
    op_j = row.operator("gta5_trains.add_point", text="Junction", icon="DECORATE_DRIVER")
    op_j.flag = 4
    box.operator("gta5_trains.mark_junction", text="Toggle Selected Junction", icon="DECORATE_DRIVER")
    box.operator("gta5_trains.sync_from_curve", text="Sync from Curve", icon="FILE_REFRESH")
    box.operator("gta5_trains.generate_from_curve", text="Generate from Active Curve", icon="CURVE_BEZCURVE")

    # Points
    box = layout.box()
    box.label(text=f"Points ({props.stat_points})", icon="CURVE_PATH")
    row = box.row()
    row.template_list("GTA5_UL_TRAINS_Points", "", props, "points", props, "point_index", rows=6)
    col = row.column(align=True)
    col.operator("gta5_trains.remove_point", text="", icon="REMOVE")
    if 0 <= props.point_index < len(props.points):
        pt = props.points[props.point_index]
        sub = box.box()
        sub.label(text=f"Point {props.point_index}")
        sub.prop(pt, "position")
        sub.prop(pt, "flag")
        sub.operator("gta5_trains.mark_junction", text="Toggle Junction", icon="DECORATE_DRIVER")


# ── HELP ─────────────────────────────────────────────────────────────────────

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
    # Start timer for auto-updating YNV flags
    bpy.app.timers.register(update_ynv_flags)

def unregister():
    # Stop timer
    if bpy.app.timers.is_registered(update_ynv_flags):
        bpy.app.timers.unregister(update_ynv_flags)
    for cls in reversed(_classes):
        try: bpy.utils.unregister_class(cls)
        except Exception: pass
