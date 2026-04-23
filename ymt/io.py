import xml.etree.ElementTree as ET

from ..shared.xml_utils import fval, ival, sval, bval, sub_val, sub_text, to_xml_string


def _parse_ymt_xml(filepath, props):
    props.scenario_points.clear()
    props.chaining_nodes.clear()
    props.chaining_edges.clear()
    props.chains.clear()
    props.entity_overrides.clear()

    try:
        tree = ET.parse(filepath)
    except ET.ParseError as e:
        return False, str(e)

    root = tree.getroot()
    if root.tag != "CScenarioPointRegion":
        return False, f"Expected CScenarioPointRegion root, found {root.tag}"

    props.version_number = ival(root, "VersionNumber", 80)

    points_section = root.find("Points")
    if points_section is not None:
        my_points = points_section.find("MyPoints")
        if my_points is not None:
            for item in my_points.findall("Item"):
                sp = props.scenario_points.add()
                sp.itype = ival(item, "iType", 1)
                sp.model_set_id = ival(item, "ModelSetId", 0)
                sp.interior_id = ival(item, "iInterior", 0)
                sp.imap_id = ival(item, "iRequiredIMapId", 0)
                sp.probability = ival(item, "iProbability", 0)
                sp.avail_mp_sp = ival(item, "uAvailableInMpSp", 1)
                sp.time_start = ival(item, "iTimeStartOverride", 0)
                sp.time_end = ival(item, "iTimeEndOverride", 24)
                sp.radius = ival(item, "iRadius", 0)
                sp.time_till_leaves = ival(item, "iTimeTillPedLeaves", 255)
                sp.scenario_group = ival(item, "iScenarioGroup", 0)
                flags_el = item.find("Flags")
                sp.flags = (flags_el.text or "").strip() if flags_el is not None else ""
                pos_el = item.find("vPositionAndDirection")
                if pos_el is not None:
                    sp.position = (
                        float(pos_el.get("x", 0)),
                        float(pos_el.get("y", 0)),
                        float(pos_el.get("z", 0)),
                        float(pos_el.get("w", 0)),
                    )

    eo_section = root.find("EntityOverrides")
    if eo_section is not None:
        for item in eo_section.findall("Item"):
            eo = props.entity_overrides.add()
            et_el = item.find("EntityType")
            eo.entity_type = (et_el.text or "").strip() if et_el is not None else ""
            ep_el = item.find("EntityPosition")
            if ep_el is not None:
                eo.entity_position = (
                    float(ep_el.get("x", 0)),
                    float(ep_el.get("y", 0)),
                    float(ep_el.get("z", 0)),
                )
            eo.may_not_exist = bval(item, "EntityMayNotAlwaysExist", True)
            eo.prevent_art = bval(item, "SpecificallyPreventArtPoints", False)

    cg = root.find("ChainingGraph")
    if cg is not None:
        nodes_el = cg.find("Nodes")
        if nodes_el is not None:
            for item in nodes_el.findall("Item"):
                cn = props.chaining_nodes.add()
                pos = item.find("Position")
                if pos is not None:
                    cn.position = (float(pos.get("x", 0)), float(pos.get("y", 0)), float(pos.get("z", 0)))
                st = item.find("ScenarioType")
                cn.scenario_type = (st.text or "standing").strip() if st is not None else "standing"
                hi = item.find("HasIncomingEdges")
                cn.has_incoming = (hi.get("value", "false").lower() == "true") if hi is not None else False
                ho = item.find("HasOutgoingEdges")
                cn.has_outgoing = (ho.get("value", "true").lower() == "true") if ho is not None else True

        edges_el = cg.find("Edges")
        if edges_el is not None:
            for item in edges_el.findall("Item"):
                ce = props.chaining_edges.add()
                ce.node_from = ival(item, "NodeIndexFrom", 0)
                ce.node_to = ival(item, "NodeIndexTo", 0)
                ce.action = ival(item, "Action", 0)
                ce.nav_mode = ival(item, "NavMode", 1)
                ce.nav_speed = ival(item, "NavSpeed", 2)

        chains_el = cg.find("Chains")
        if chains_el is not None:
            for item in chains_el.findall("Item"):
                ch = props.chains.add()
                hk = item.find("hash_44F1B77A")
                ch.hash_name = hk.get("value", "") if hk is not None else ""
                ei = item.find("EdgeIds")
                ch.edge_ids = (ei.text or "").strip() if ei is not None else ""

    ag = root.find("AccelGrid")
    if ag is not None:
        props.accel_min_cell_x = ival(ag, "MinCellX", -4)
        props.accel_max_cell_x = ival(ag, "MaxCellX", 5)
        props.accel_min_cell_y = ival(ag, "MinCellY", -64)
        props.accel_max_cell_y = ival(ag, "MaxCellY", -48)
        props.accel_cell_dim_x = ival(ag, "CellDimX", 32)
        props.accel_cell_dim_y = ival(ag, "CellDimY", 32)

    lu = root.find("LookUps")
    if lu is not None:
        def _collect(tag):
            sec = lu.find(tag)
            return "\n".join((i.text or "").strip() for i in sec.findall("Item")) if sec is not None else ""

        props.type_names = _collect("TypeNames")
        props.ped_modelset_names = _collect("PedModelSetNames")
        props.veh_modelset_names = _collect("VehicleModelSetNames")

    props.stat_points = len(props.scenario_points)
    props.stat_nodes = len(props.chaining_nodes)
    props.stat_edges = len(props.chaining_edges)
    props.stat_chains = len(props.chains)
    return True, "OK"


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
                sp.time_end = obj.get("time_end", sp.time_end)
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
        sub_val(item, "iType", sp.itype)
        sub_val(item, "ModelSetId", sp.model_set_id)
        sub_val(item, "iInterior", sp.interior_id)
        sub_val(item, "iRequiredIMapId", sp.imap_id)
        sub_val(item, "iProbability", sp.probability)
        sub_val(item, "uAvailableInMpSp", sp.avail_mp_sp)
        sub_val(item, "iTimeStartOverride", sp.time_start)
        sub_val(item, "iTimeEndOverride", sp.time_end)
        sub_val(item, "iRadius", sp.radius)
        sub_val(item, "iTimeTillPedLeaves", sp.time_till_leaves)
        sub_val(item, "iScenarioGroup", sp.scenario_group)
        ET.SubElement(item, "Flags").text = sp.flags
        pos_el = ET.SubElement(item, "vPositionAndDirection")
        pos_el.set("x", f"{sp.position[0]:.7g}")
        pos_el.set("y", f"{sp.position[1]:.7g}")
        pos_el.set("z", f"{sp.position[2]:.7g}")
        pos_el.set("w", f"{sp.position[3]:.7g}")

    eo_el = ET.SubElement(root, "EntityOverrides", itemType="CScenarioEntityOverride")
    for eo in props.entity_overrides:
        item = ET.SubElement(eo_el, "Item")
        ep = ET.SubElement(item, "EntityPosition")
        ep.set("x", f"{eo.entity_position[0]:.7g}")
        ep.set("y", f"{eo.entity_position[1]:.7g}")
        ep.set("z", f"{eo.entity_position[2]:.7g}")
        sub_text(item, "EntityType", eo.entity_type)
        ET.SubElement(item, "ScenarioPoints", itemType="CExtensionDefSpawnPoint")
        sub_val(item, "EntityMayNotAlwaysExist", str(eo.may_not_exist).lower())
        sub_val(item, "SpecificallyPreventArtPoints", str(eo.prevent_art).lower())

    cg_el = ET.SubElement(root, "ChainingGraph")
    nodes_el = ET.SubElement(cg_el, "Nodes", itemType="CScenarioChainingNode")
    for cn in props.chaining_nodes:
        item = ET.SubElement(nodes_el, "Item")
        pos_el = ET.SubElement(item, "Position")
        pos_el.set("x", f"{cn.position[0]:.7g}")
        pos_el.set("y", f"{cn.position[1]:.7g}")
        pos_el.set("z", f"{cn.position[2]:.7g}")
        ET.SubElement(item, "hash_9B1D60AB")
        sub_text(item, "ScenarioType", cn.scenario_type)
        sub_val(item, "HasIncomingEdges", str(cn.has_incoming).lower())
        sub_val(item, "HasOutgoingEdges", str(cn.has_outgoing).lower())

    edges_el = ET.SubElement(cg_el, "Edges", itemType="CScenarioChainingEdge")
    for ce in props.chaining_edges:
        item = ET.SubElement(edges_el, "Item")
        sub_val(item, "NodeIndexFrom", ce.node_from)
        sub_val(item, "NodeIndexTo", ce.node_to)
        sub_val(item, "Action", ce.action)
        sub_val(item, "NavMode", ce.nav_mode)
        sub_val(item, "NavSpeed", ce.nav_speed)

    chains_el = ET.SubElement(cg_el, "Chains", itemType="CScenarioChain")
    for ch in props.chains:
        item = ET.SubElement(chains_el, "Item")
        sub_val(item, "hash_44F1B77A", ch.hash_name)
        ET.SubElement(item, "EdgeIds").text = ch.edge_ids

    ag_el = ET.SubElement(root, "AccelGrid")
    sub_val(ag_el, "MinCellX", props.accel_min_cell_x)
    sub_val(ag_el, "MaxCellX", props.accel_max_cell_x)
    sub_val(ag_el, "MinCellY", props.accel_min_cell_y)
    sub_val(ag_el, "MaxCellY", props.accel_max_cell_y)
    sub_val(ag_el, "CellDimX", props.accel_cell_dim_x)
    sub_val(ag_el, "CellDimY", props.accel_cell_dim_y)

    ET.SubElement(root, "hash_E529D603")
    ET.SubElement(root, "Clusters", itemType="CScenarioPointCluster")

    lu_el = ET.SubElement(root, "LookUps")

    def _write_names(tag, names_str):
        sec = ET.SubElement(lu_el, tag)
        for name in names_str.split("\n"):
            name = name.strip()
            if name:
                sub_text(sec, "Item", name)

    _write_names("TypeNames", props.type_names)
    _write_names("PedModelSetNames", props.ped_modelset_names)
    _write_names("VehicleModelSetNames", props.veh_modelset_names)
    ET.SubElement(lu_el, "GroupNames")
    ET.SubElement(lu_el, "InteriorNames")
    ET.SubElement(lu_el, "RequiredIMapNames")

    return to_xml_string(root)
