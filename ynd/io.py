import xml.etree.ElementTree as ET

from ..shared.properties import PED_SPECIAL_TYPES
from ..shared.xml_utils import fval, ival, sval, sub_text, sub_val, to_xml_string


def _apply_node_flags(
    n: "bpy.types.PropertyGroup",
    f0: int,
    f1: int,
    f2: int,
    f3: int,
    f4: int,
    f5: int,
) -> None:
    n.flags0.from_int(f0)
    n.flags1.from_int(f1)
    n.flags2.from_int(f2)
    n.flags3.from_int(f3)
    n.flags4.from_int(f4)
    n.flags5.from_int(f5)
    n.raw0 = f0
    n.raw1 = f1
    n.raw2 = f2
    n.raw3 = f3
    n.raw4 = f4
    n.raw5 = f5


def _node_flags_to_ints(n):
    f0 = n.flags0.to_int()
    f1 = n.flags1.to_int()
    f2 = n.flags2.to_int()
    f3 = n.flags3.to_int()
    f4 = n.flags4.to_int()
    f5 = n.flags5.to_int()

    raw1 = int(getattr(n, "raw1", f1))
    raw5 = int(getattr(n, "raw5", f5))

    raw_special = (raw1 >> 3) & 0x1F
    known_special = {0, 2, 10, 14, 15, 16, 17, 18, 19, 20}
    if getattr(n.flags1, "special_type", "NONE") == "NONE" and raw_special not in known_special:
        f1 = (f1 & 0x07) | (raw1 & 0xF8)

    f5 = (f5 & 0x07) | (raw5 & 0xF8)

    return f0, f1, f2, f3, f4, f5


def _apply_link_flags(lk: "bpy.types.PropertyGroup", f0: int, f1: int, f2: int) -> None:
    lk.flags0.from_int(f0)
    lk.flags1.from_int(f1)
    lk.flags2.from_int(f2)
    lk.raw_flags0 = f0
    lk.raw_flags1 = f1
    lk.raw_flags2 = f2


def _link_flags_to_ints(lk):
    return lk.flags0.to_int(), lk.flags1.to_int(), lk.flags2.to_int()


def _node_is_vehicle(n):
    return n.flags1.special_type not in PED_SPECIAL_TYPES


def _node_is_freeway(n):
    return n.flags2.freeway


def _node_is_junction(n):
    return n.flags2.junction


def _update_ynd_stats(props: "bpy.types.PropertyGroup") -> None:
    nodes = props.nodes
    props.stat_nodes = len(nodes)
    props.stat_vehicle = sum(1 for n in nodes if _node_is_vehicle(n))
    props.stat_ped = sum(1 for n in nodes if not _node_is_vehicle(n))
    props.stat_junctions = sum(1 for n in nodes if _node_is_junction(n))


def _parse_ynd_xml(filepath, props):
    from .builders import _find_node_by_area_id

    props.nodes.clear()
    try:
        tree = ET.parse(filepath)
    except ET.ParseError as e:
        return False, str(e)
    root = tree.getroot()
    if root.tag != "NodeDictionary":
        return False, f"Expected NodeDictionary root, found {root.tag}"

    nodes_el = root.find("Nodes")
    if nodes_el is not None:
        for node_el in nodes_el.findall("Item"):
            n = props.nodes.add()
            n.area_id = ival(node_el, "AreaID", 400)
            n.node_id = ival(node_el, "NodeID", 0)
            n.street_name = sval(node_el, "StreetName", "")
            f0 = ival(node_el, "Flags0", 2)
            f1 = ival(node_el, "Flags1", 0)
            f2 = ival(node_el, "Flags2", 0)
            f3 = ival(node_el, "Flags3", 64)
            f4 = ival(node_el, "Flags4", 134)
            f5 = ival(node_el, "Flags5", 2)
            pos = node_el.find("Position")
            if pos is not None:
                n.position = (float(pos.get("x", 0)), float(pos.get("y", 0)), float(pos.get("z", 0)))
            _apply_node_flags(n, f0, f1, f2, f3, f4, f5)
            links_el = node_el.find("Links")
            if links_el is not None:
                for link_el in links_el.findall("Item"):
                    lk = n.links.add()
                    lk.to_area_id = ival(link_el, "ToAreaID", n.area_id)
                    lk.to_node_id = ival(link_el, "ToNodeID", 0)
                    lk.link_length = ival(link_el, "LinkLength", 10)
                    lf0 = ival(link_el, "Flags0", 0)
                    lf1 = ival(link_el, "Flags1", 0)
                    lf2 = ival(link_el, "Flags2", 0)
                    _apply_link_flags(lk, lf0, lf1, lf2)

    junctions = []
    junctions_el = root.find("Junctions")
    if junctions_el is not None:
        for junction_el in junctions_el.findall("Item"):
            pos_el = junction_el.find("Position")
            junctions.append(
                {
                    "min_z": fval(junction_el, "MinZ", 0.0),
                    "max_z": fval(junction_el, "MaxZ", 0.0),
                    "pos_x": float(pos_el.get("x", 0.0)) if pos_el is not None else 0.0,
                    "pos_y": float(pos_el.get("y", 0.0)) if pos_el is not None else 0.0,
                    "size_x": ival(junction_el, "SizeX", 8),
                    "size_y": ival(junction_el, "SizeY", 8),
                    "heightmap": sval(junction_el, "Heightmap", "").strip(),
                }
            )

    refs_el = root.find("JunctionRefs")
    if refs_el is not None:
        for ref_el in refs_el.findall("Item"):
            junction_id = ival(ref_el, "JunctionID", -1)
            if not (0 <= junction_id < len(junctions)):
                continue

            _index, node = _find_node_by_area_id(
                props.nodes,
                ival(ref_el, "AreaID", -1),
                ival(ref_el, "NodeID", -1),
            )
            if node is None:
                continue

            junction = junctions[junction_id]
            node.flags2.junction = True
            node.flags5.has_junction_heightmap = True
            node.junction.min_z = junction["min_z"]
            node.junction.max_z = junction["max_z"]
            node.junction.pos_x = junction["pos_x"]
            node.junction.pos_y = junction["pos_y"]
            node.junction.size_x = junction["size_x"]
            node.junction.size_y = junction["size_y"]
            node.junction.heightmap = junction["heightmap"]
            node.junction.ref_unk0 = ival(ref_el, "Unk0", 0)

    _update_ynd_stats(props)
    return True, "OK"


def _build_ynd_xml(context, props):
    from .builders import _sync_positions_from_node_objects

    _sync_positions_from_node_objects(context, props)

    root = ET.Element("NodeDictionary")
    sub_val(root, "VehicleNodeCount", sum(1 for n in props.nodes if _node_is_vehicle(n)))
    sub_val(root, "PedNodeCount", sum(1 for n in props.nodes if not _node_is_vehicle(n)))

    nodes_el = ET.SubElement(root, "Nodes")
    for node in props.nodes:
        item = ET.SubElement(nodes_el, "Item")
        sub_val(item, "AreaID", node.area_id)
        sub_val(item, "NodeID", node.node_id)
        ET.SubElement(item, "StreetName").text = node.street_name
        pos = ET.SubElement(item, "Position")
        pos.set("x", f"{node.position[0]:.6f}")
        pos.set("y", f"{node.position[1]:.6f}")
        pos.set("z", f"{node.position[2]:.6f}")
        f0, f1, f2, f3, f4, f5 = _node_flags_to_ints(node)
        for fi, fv in enumerate([f0, f1, f2, f3, f4, f5]):
            sub_val(item, f"Flags{fi}", fv)
        links_el = ET.SubElement(item, "Links")
        for lk in node.links:
            litem = ET.SubElement(links_el, "Item")
            sub_val(litem, "ToAreaID", lk.to_area_id)
            sub_val(litem, "ToNodeID", lk.to_node_id)
            lf0, lf1, lf2 = _link_flags_to_ints(lk)
            sub_val(litem, "Flags0", lf0)
            sub_val(litem, "Flags1", lf1)
            sub_val(litem, "Flags2", lf2)
            sub_val(litem, "LinkLength", lk.link_length)

    junction_nodes = [node for node in props.nodes if node.flags2.junction and node.flags5.has_junction_heightmap]
    junctions_el = ET.SubElement(root, "Junctions")
    refs_el = ET.SubElement(root, "JunctionRefs")
    for junction_id, node in enumerate(junction_nodes):
        junction_item = ET.SubElement(junctions_el, "Item")
        position = ET.SubElement(junction_item, "Position")
        position.set("x", f"{node.junction.pos_x:.6f}")
        position.set("y", f"{node.junction.pos_y:.6f}")
        sub_val(junction_item, "MinZ", node.junction.min_z)
        sub_val(junction_item, "MaxZ", node.junction.max_z)
        sub_val(junction_item, "SizeX", node.junction.size_x)
        sub_val(junction_item, "SizeY", node.junction.size_y)
        sub_text(junction_item, "Heightmap", node.junction.heightmap)

        ref_item = ET.SubElement(refs_el, "Item")
        sub_val(ref_item, "AreaID", node.area_id)
        sub_val(ref_item, "NodeID", node.node_id)
        sub_val(ref_item, "JunctionID", junction_id)
        sub_val(ref_item, "Unk0", node.junction.ref_unk0)
    return to_xml_string(root)
