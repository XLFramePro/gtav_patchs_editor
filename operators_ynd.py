"""
operators_ynd.py — Complete PathNodes YND with structured flags (ynd reference).
Import/Export XML, full node/link management, auto ped/vehicle detection.
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

def _apply_node_flags(
    n: "bpy.types.PropertyGroup",
    f0: int, f1: int, f2: int, f3: int, f4: int, f5: int,
) -> None:
    """Decode 6 raw flag bytes into the node's PropertyGroup sub-groups."""
    n.flags0.from_int(f0)
    n.flags1.from_int(f1)
    n.flags2.from_int(f2)
    n.flags3.from_int(f3)
    n.flags4.from_int(f4)
    n.flags5.from_int(f5)
    # Keep raw mirrors for potential low-level I/O access.
    n.raw0 = f0; n.raw1 = f1; n.raw2 = f2
    n.raw3 = f3; n.raw4 = f4; n.raw5 = f5


def _node_flags_to_ints(n):
    """Convert PropertyGroups back to 6 ints for XML export."""
    f0 = n.flags0.to_int()
    f1 = n.flags1.to_int()
    f2 = n.flags2.to_int()
    f3 = n.flags3.to_int()
    f4 = n.flags4.to_int()
    f5 = n.flags5.to_int()
    return f0, f1, f2, f3, f4, f5


def _apply_link_flags(lk: "bpy.types.PropertyGroup", f0: int, f1: int, f2: int) -> None:
    """Decode 3 raw flag bytes into the link's PropertyGroup sub-groups."""
    lk.flags0.from_int(f0)
    lk.flags1.from_int(f1)
    lk.flags2.from_int(f2)
    lk.raw_flags0 = f0; lk.raw_flags1 = f1; lk.raw_flags2 = f2


def _link_flags_to_ints(lk):
    return lk.flags0.to_int(), lk.flags1.to_int(), lk.flags2.to_int()


def _node_is_vehicle(n):
    return n.flags1.special_type not in PED_SPECIAL_TYPES


def _node_is_freeway(n):
    return n.flags2.freeway

def _node_is_junction(n):
    return n.flags2.junction


def _update_ynd_stats(props: "bpy.types.PropertyGroup") -> None:
    """Recompute all YND_Props stat counters from the current node list."""
    nodes = props.nodes
    props.stat_nodes     = len(nodes)
    props.stat_vehicle   = sum(1 for n in nodes if _node_is_vehicle(n))
    props.stat_ped       = sum(1 for n in nodes if not _node_is_vehicle(n))
    props.stat_junctions = sum(1 for n in nodes if _node_is_junction(n))


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
        return False, f"Expected NodeDictionary root, found {root.tag}"

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

    junctions = []
    junctions_el = root.find("Junctions")
    if junctions_el is not None:
        for junction_el in junctions_el.findall("Item"):
            pos_el = junction_el.find("Position")
            junctions.append({
                "min_z": fval(junction_el, "MinZ", 0.0),
                "max_z": fval(junction_el, "MaxZ", 0.0),
                "pos_x": float(pos_el.get("x", 0.0)) if pos_el is not None else 0.0,
                "pos_y": float(pos_el.get("y", 0.0)) if pos_el is not None else 0.0,
                "size_x": ival(junction_el, "SizeX", 8),
                "size_y": ival(junction_el, "SizeY", 8),
                "heightmap": sval(junction_el, "Heightmap", "").strip(),
            })

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


def _find_node_by_area_id(nodes, area_id, node_id):
    for i, n in enumerate(nodes):
        if n.area_id == area_id and n.node_id == node_id:
            return i, n
    return None, None


def _next_free_node_id(nodes, area_id):
    """Return the smallest free node_id for a given area."""
    used = {int(n.node_id) for n in nodes if int(n.area_id) == int(area_id)}
    nid = 0
    while nid in used:
        nid += 1
    return nid


def _build_node_index_map(nodes):
    """Map (area_id, node_id) -> node index for stable object syncing."""
    index_map = {}
    for i, n in enumerate(nodes):
        index_map[(int(n.area_id), int(n.node_id))] = i
    return index_map


YND_CURVE_PRESETS = {
    "TWO_LANES": {
        "node": (2, 0, 0, 150, 3, 2),
        "link": (4, 0, 72),
    },
    "ONE_EACH": {
        "node": (2, 0, 0, 150, 3, 2),
        "link": (4, 0, 36),
    },
    "CENTER_ONE": {
        "node": (2, 0, 0, 150, 3, 2),
        "link": (4, 0, 32),
    },
    "CENTER_TWO": {
        "node": (2, 0, 0, 150, 3, 2),
        "link": (4, 0, 64),
    },
    "CENTER_THREE": {
        "node": (2, 0, 0, 150, 3, 2),
        "link": (4, 0, 96),
    },
    "NO_TRAFFIC": {
        "node": (2, 0, 0, 150, 3, 2),
        "link": (4, 0, 32),
    },
    "BOATS": {
        "node": (0, 0, 176, 212, 15, 2),
        "link": (4, 0, 36),
        "first_node": (0, 160, 180, 142, 15, 3),
        "last_node": (0, 160, 180, 142, 15, 3),
        "end_link": (0, 0, 36),
    },
    "PARKING": {
        "node": (35, 0, 144, 10, 116, 2),
        "link": (144, 8, 36),
        "last_node": (35, 0, 144, 232, 116, 2),
    },
}


def _calc_area_id_from_position(position):
    """Convert world XY to GTA V YND area index on the 32x32 grid."""
    x, y = float(position[0]), float(position[1])
    cell_x = max(0, min(31, int(math.floor((x + 8192.0) / 512.0))))
    cell_y = max(0, min(31, int(math.floor((y + 8192.0) / 512.0))))
    return (cell_y * 32) + cell_x


def _iter_curve_point_chains(curve_obj):
    """Yield one world-space point chain per spline in a Blender Curve."""
    for spline in curve_obj.data.splines:
        points = []
        if spline.type == "POLY":
            for point in spline.points:
                points.append(tuple(curve_obj.matrix_world @ Vector(point.co[:3])))
        elif spline.type == "BEZIER":
            for point in spline.bezier_points:
                points.append(tuple(curve_obj.matrix_world @ point.co))
        if points:
            yield points


def _preset_node_flags(preset_key, point_index, point_count):
    preset = YND_CURVE_PRESETS[preset_key]
    if preset_key == "BOATS":
        if point_index == 0:
            return preset["first_node"]
        if point_index == point_count - 1:
            return preset["last_node"]
    if preset_key == "PARKING" and point_index == point_count - 1:
        return preset["last_node"]
    return preset["node"]


def _preset_link_flags(preset_key, source_index, target_index, point_count):
    preset = YND_CURVE_PRESETS[preset_key]
    if preset_key == "BOATS":
        if source_index in {0, point_count - 1} or target_index in {0, point_count - 1}:
            return preset["end_link"]
    return preset["link"]


def _snapshot_curve_node_state(props):
    """Capture generated curve node state so sync can preserve manual edits."""
    snapshot = {}
    fallback_index = 0

    for node in props.nodes:
        chain_index = int(getattr(node, "curve_chain_index", -1))
        point_index = int(getattr(node, "curve_point_index", -1))
        key = (chain_index, point_index) if chain_index >= 0 and point_index >= 0 else ("flat", fallback_index)
        fallback_index += 1

        node_state = {
            "area_id": int(node.area_id),
            "node_id": int(node.node_id),
            "street_name": node.street_name,
            "flags": _node_flags_to_ints(node),
            "links": {},
            "extra_links": [],
            "junction": {
                "min_z": float(node.junction.min_z),
                "max_z": float(node.junction.max_z),
                "pos_x": float(node.junction.pos_x),
                "pos_y": float(node.junction.pos_y),
                "size_x": int(node.junction.size_x),
                "size_y": int(node.junction.size_y),
                "heightmap": node.junction.heightmap,
                "ref_unk0": int(node.junction.ref_unk0),
            },
        }

        for link in node.links:
            target_index, target = _find_node_by_area_id(props.nodes, link.to_area_id, link.to_node_id)
            if target is None:
                continue

            target_chain = int(getattr(target, "curve_chain_index", -1))
            target_point = int(getattr(target, "curve_point_index", -1))
            if chain_index >= 0 and target_chain == chain_index and target_point >= 0:
                delta = target_point - point_index
                relation = "prev" if delta == -1 else "next" if delta == 1 else None
            else:
                relation = None

            if relation is None:
                target_key = _curve_node_key(target)
                if target_key is not None:
                    node_state["extra_links"].append({
                        "target_key": target_key,
                        "flags": _link_flags_to_ints(link),
                        "length": int(link.link_length),
                    })
                continue

            node_state["links"][relation] = {
                "flags": _link_flags_to_ints(link),
            }

        snapshot[key] = node_state

    return snapshot


def _next_preserved_or_free_node_id(snapshot_state, used_by_area, area_id):
    """Reuse previous node_id when possible, otherwise allocate a free one."""
    used = used_by_area.setdefault(int(area_id), set())
    if snapshot_state is not None and int(snapshot_state["area_id"]) == int(area_id):
        old_id = int(snapshot_state["node_id"])
        if old_id not in used:
            used.add(old_id)
            return old_id

    node_id = 0
    while node_id in used:
        node_id += 1
    used.add(node_id)
    return node_id


def _flat_curve_point_keys(point_chains):
    flat_keys = []
    for chain_index, chain in enumerate(point_chains):
        for point_index, _position in enumerate(chain):
            flat_keys.append((chain_index, point_index))
    return flat_keys


def _curve_node_key(node):
    chain_index = int(getattr(node, "curve_chain_index", -1))
    point_index = int(getattr(node, "curve_point_index", -1))
    if chain_index < 0 or point_index < 0:
        return None
    return chain_index, point_index


def _collect_curve_neighbor_relations(chain_index, point_index, point_count, bidirectional):
    relations = []
    if bidirectional and point_index > 0:
        relations.append(("prev", (chain_index, point_index - 1)))
    if point_index < point_count - 1:
        relations.append(("next", (chain_index, point_index + 1)))
    return relations


def _populate_ynd_from_curve(curve_obj, props, preset_key, bidirectional=True, preserve_existing=False):
    """Create a YND chain from a Blender curve using Max-like presets."""
    point_chains = list(_iter_curve_point_chains(curve_obj))
    total_points = sum(len(chain) for chain in point_chains)
    if total_points < 2:
        return False, "The active curve must contain at least 2 control points."
    if preset_key == "PARKING" and total_points != 2:
        return False, "Parking preset requires exactly 2 control points."

    existing_state = _snapshot_curve_node_state(props) if preserve_existing else {}
    if preserve_existing and existing_state:
        flat_existing = list(existing_state.values())
        flat_keys = _flat_curve_point_keys(point_chains)
        if not any(isinstance(key[0], int) for key in existing_state.keys()) and len(flat_existing) == len(flat_keys):
            existing_state = {flat_keys[i]: flat_existing[i] for i in range(len(flat_keys))}

    props.nodes.clear()
    created = []
    created_by_key = {}
    first_area_id = None
    used_ids_by_area = {}

    for chain_index, chain in enumerate(point_chains):
        if len(chain) < 2:
            continue

        chain_nodes = []
        for point_index, position in enumerate(chain):
            area_id = _calc_area_id_from_position(position)
            state_key = (chain_index, point_index)
            previous_state = existing_state.get(state_key)
            node_id = _next_preserved_or_free_node_id(previous_state, used_ids_by_area, area_id)
            node = props.nodes.add()
            node.area_id = area_id
            node.node_id = node_id
            node.curve_chain_index = chain_index
            node.curve_point_index = point_index
            node.position = position
            if previous_state is not None:
                node.street_name = previous_state["street_name"]
                _apply_node_flags(node, *previous_state["flags"])
                node.junction.min_z = previous_state["junction"]["min_z"]
                node.junction.max_z = previous_state["junction"]["max_z"]
                node.junction.pos_x = previous_state["junction"]["pos_x"]
                node.junction.pos_y = previous_state["junction"]["pos_y"]
                node.junction.size_x = previous_state["junction"]["size_x"]
                node.junction.size_y = previous_state["junction"]["size_y"]
                node.junction.heightmap = previous_state["junction"]["heightmap"]
                node.junction.ref_unk0 = previous_state["junction"]["ref_unk0"]
            else:
                node.street_name = curve_obj.name
                _apply_node_flags(node, *_preset_node_flags(preset_key, point_index, len(chain)))
            chain_nodes.append(node)
            created.append(node)
            created_by_key[state_key] = node
            if first_area_id is None:
                first_area_id = area_id

        for index, node in enumerate(chain_nodes):
            neighbor_indices = []
            if bidirectional and index > 0:
                neighbor_indices.append(index - 1)
            if index < len(chain_nodes) - 1:
                neighbor_indices.append(index + 1)

            for target_index in neighbor_indices:
                target = chain_nodes[target_index]
                link = node.links.add()
                link.to_area_id = target.area_id
                link.to_node_id = target.node_id
                relation = "prev" if target_index < index else "next"
                previous_link = existing_state.get((chain_index, index), {}).get("links", {}).get(relation)
                default_length = int(min(255, max(1.0, (Vector(node.position) - Vector(target.position)).length)))
                link.link_length = default_length
                if previous_link is not None:
                    _apply_link_flags(link, *previous_link["flags"])
                else:
                    _apply_link_flags(link, *_preset_link_flags(preset_key, index, target_index, len(chain_nodes)))

    if preserve_existing:
        for state_key, previous_state in existing_state.items():
            node = created_by_key.get(state_key)
            if node is None:
                continue

            existing_pairs = {
                (int(link.to_area_id), int(link.to_node_id))
                for link in node.links
            }
            for extra_link in previous_state.get("extra_links", []):
                target = created_by_key.get(tuple(extra_link["target_key"]))
                if target is None:
                    continue
                target_pair = (int(target.area_id), int(target.node_id))
                if target_pair in existing_pairs:
                    continue

                link = node.links.add()
                link.to_area_id = target.area_id
                link.to_node_id = target.node_id
                link.link_length = extra_link["length"]
                _apply_link_flags(link, *extra_link["flags"])
                existing_pairs.add(target_pair)

    if not created:
        return False, "The active curve must contain at least one spline with 2 control points."

    props.area_id = first_area_id if first_area_id is not None else props.area_id
    props.node_index = 0 if created else -1
    _update_ynd_stats(props)
    return True, f"Generated {len(created)} nodes from curve '{curve_obj.name}'"


def _find_ynd_source_curve(context):
    """Return the active curve, or the most recent tagged YND source curve."""
    active = context.active_object
    if active is not None and active.type == "CURVE":
        return active

    for obj in context.scene.objects:
        if obj.type == "CURVE" and obj.get("ynd_type") == "source_curve":
            return obj

    return None


def _recalc_all_link_lengths(props):
    """Recalculate all link lengths from current node positions."""
    pos_map = {
        (int(node.area_id), int(node.node_id)): Vector(node.position)
        for node in props.nodes
    }
    recalc = 0
    for node in props.nodes:
        src_pos = Vector(node.position)
        for link in node.links:
            dst_pos = pos_map.get((int(link.to_area_id), int(link.to_node_id)))
            if dst_pos is None:
                continue
            link.link_length = min(255, max(1, int(round((src_pos - dst_pos).length))))
            recalc += 1
    return recalc


def _update_curve_links_only(curve_obj, props, preset_key, bidirectional=True):
    """Update only adjacency links for curve-tracked nodes and preserve manual extras."""
    point_chains = list(_iter_curve_point_chains(curve_obj))
    tracked_nodes = {
        key: node
        for node in props.nodes
        for key in [_curve_node_key(node)]
        if key is not None
    }
    expected_keys = _flat_curve_point_keys(point_chains)
    if set(tracked_nodes.keys()) != set(expected_keys):
        return False, "Curve topology changed; use Sync from Curve to rebuild nodes."

    existing_state = _snapshot_curve_node_state(props)
    for chain_index, chain in enumerate(point_chains):
        for point_index, position in enumerate(chain):
            node = tracked_nodes[(chain_index, point_index)]
            node.position = position
            node.links.clear()

    for chain_index, chain in enumerate(point_chains):
        point_count = len(chain)
        for point_index in range(point_count):
            node = tracked_nodes[(chain_index, point_index)]
            previous_state = existing_state.get((chain_index, point_index), {})
            for relation, target_key in _collect_curve_neighbor_relations(chain_index, point_index, point_count, bidirectional):
                target = tracked_nodes[target_key]
                link = node.links.add()
                link.to_area_id = target.area_id
                link.to_node_id = target.node_id
                link.link_length = int(min(255, max(1.0, (Vector(node.position) - Vector(target.position)).length)))
                preserved = previous_state.get("links", {}).get(relation)
                if preserved is not None:
                    _apply_link_flags(link, *preserved["flags"])
                else:
                    _apply_link_flags(link, *_preset_link_flags(preset_key, point_index, target_key[1], point_count))

            existing_pairs = {
                (int(link.to_area_id), int(link.to_node_id))
                for link in node.links
            }
            for extra_link in previous_state.get("extra_links", []):
                target = tracked_nodes.get(tuple(extra_link["target_key"]))
                if target is None:
                    continue
                target_pair = (int(target.area_id), int(target.node_id))
                if target_pair in existing_pairs:
                    continue
                link = node.links.add()
                link.to_area_id = target.area_id
                link.to_node_id = target.node_id
                link.link_length = extra_link["length"]
                _apply_link_flags(link, *extra_link["flags"])
                existing_pairs.add(target_pair)

    return True, f"Updated links for {len(tracked_nodes)} curve node(s)"


def _find_node_index_for_object(obj, props, node_index_map):
    """Resolve node index from object custom props with stable-id fallback."""
    area = obj.get("node_area_id")
    node_id = obj.get("node_id")
    if area is not None and node_id is not None:
        idx = node_index_map.get((int(area), int(node_id)))
        if idx is not None:
            return idx

    idx = obj.get("node_index", -1)
    if 0 <= idx < len(props.nodes):
        n = props.nodes[idx]
        if area is None or node_id is None:
            return idx
        if int(n.area_id) == int(area) and int(n.node_id) == int(node_id):
            return idx

    return -1


def _sync_positions_from_node_objects(context, props):
    """Sync node positions from empties using stable identifiers.

    Returns (synced_count, stale_count).
    """
    node_index_map = _build_node_index_map(props.nodes)
    synced = 0
    stale = 0

    for obj in context.scene.objects:
        if obj.get("ynd_type") != "node":
            continue

        idx = _find_node_index_for_object(obj, props, node_index_map)
        if idx < 0:
            stale += 1
            continue

        node = props.nodes[idx]
        node.position = tuple(obj.location)

        # Keep custom properties aligned for future operations.
        obj["node_index"] = idx
        obj["node_area_id"] = node.area_id
        obj["node_id"] = node.node_id
        synced += 1

    return synced, stale


def _prune_invalid_local_links(props):
    """Remove links that target missing nodes in the same AreaID.

    External links (to other AreaID values) are preserved.
    Returns number of removed links.
    """
    removed = 0
    node_ids_by_area = {}
    for n in props.nodes:
        node_ids_by_area.setdefault(int(n.area_id), set()).add(int(n.node_id))

    for n in props.nodes:
        local_ids = node_ids_by_area.get(int(n.area_id), set())
        bad_indices = [
            i for i, lk in enumerate(n.links)
            if int(lk.to_area_id) == int(n.area_id) and int(lk.to_node_id) not in local_ids
        ]
        for i in reversed(bad_indices):
            n.links.remove(i)
            removed += 1

    return removed


def _remove_links_targeting_node(props, area_id, node_id):
    """Remove every link in props that targets (area_id, node_id)."""
    removed = 0
    for n in props.nodes:
        idxs = [
            i for i, lk in enumerate(n.links)
            if int(lk.to_area_id) == int(area_id) and int(lk.to_node_id) == int(node_id)
        ]
        for i in reversed(idxs):
            n.links.remove(i)
            removed += 1
    return removed


def _repair_duplicate_local_ids(props):
    """Ensure node_id uniqueness per area by reassigning duplicate IDs.

    Returns number of changed node IDs.
    """
    used_by_area = {}
    changed = 0

    for n in props.nodes:
        area = int(n.area_id)
        nid = int(n.node_id)
        used = used_by_area.setdefault(area, set())
        if nid in used:
            new_id = 0
            while new_id in used:
                new_id += 1
            n.node_id = new_id
            nid = new_id
            changed += 1
        used.add(nid)

    return changed


def _build_ynd_link_objects(props, col):
    root_links = bpy.data.objects.new("YND_Links", None)
    root_links.empty_display_type = "PLAIN_AXES"
    root_links.empty_display_size = 0.1
    root_links["ynd_type"] = "links_root"
    _link_obj(root_links, col)

    for src_index, node in enumerate(props.nodes):
        start = node.position
        for link_index, lk in enumerate(node.links):
            target_index, target_node = _find_node_by_area_id(props.nodes, lk.to_area_id, lk.to_node_id)
            if target_node is None:
                continue
            curve_data = bpy.data.curves.new(f"YND_LinkCurve_{src_index}_{link_index}", type="CURVE")
            curve_data.dimensions = "3D"
            curve_data.resolution_u = 2
            curve_data.bevel_depth = 0.02
            curve_data.bevel_resolution = 0
            spline = curve_data.splines.new("POLY")
            spline.points.add(1)
            spline.points[0].co = (*start, 1.0)
            spline.points[1].co = (*target_node.position, 1.0)
            obj = bpy.data.objects.new(f"YND_Link_{node.area_id}_{node.node_id}_{lk.to_area_id}_{lk.to_node_id}", curve_data)
            obj["ynd_type"] = "link"
            obj["link_from"] = src_index
            obj["link_to"] = target_index
            obj.parent = root_links
            _link_obj(obj, col)
    return root_links


def _refresh_ynd_link_objects(props):
    """Rebuild visual link objects from current props state."""
    col = bpy.data.collections.get(YND_COLLECTION)
    if col is None:
        return

    for obj in list(col.objects):
        if obj.get("ynd_type") in {"link", "links_root"}:
            bpy.data.objects.remove(obj, do_unlink=True)

    links_root = _build_ynd_link_objects(props, col)
    root_obj = next((o for o in col.objects if o.get("ynd_type") == "root"), None)
    if root_obj is not None:
        links_root.parent = root_obj


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
        # Cubes for vehicles, spheres for pedestrians
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

    links_root = _build_ynd_link_objects(props, col)
    links_root.parent = root_obj
    return root_obj


# ─────────────────────────────────────────────────────────────────────────────
#  EXPORT XML
# ─────────────────────────────────────────────────────────────────────────────

def _build_ynd_xml(context, props):
    # Sync positions from empties with stable IDs.
    _sync_positions_from_node_objects(context, props)
    _prune_invalid_local_links(props)

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
        pos.set("x", f"{node.position[0]:.6f}")
        pos.set("y", f"{node.position[1]:.6f}")
        pos.set("z", f"{node.position[2]:.6f}")
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

    junction_nodes = [
        node for node in props.nodes
        if node.flags2.junction and node.flags5.has_junction_heightmap
    ]
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


# ─────────────────────────────────────────────────────────────────────────────
#  OPÉRATEURS
# ─────────────────────────────────────────────────────────────────────────────

class YND_OT_Import(Operator):
    """Import a PathNodes YND XML file"""
    bl_idname = "gta5_ynd.import_xml"; bl_label = "Import YND XML"
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
            f"YND imported: {props.stat_vehicle} vehicle, "
            f"{props.stat_ped} ped, {props.stat_junctions} junctions")
        return {"FINISHED"}


class YND_OT_Export(Operator):
    """Export PathNodes to YND XML"""
    bl_idname = "gta5_ynd.export_xml"; bl_label = "Export YND XML"
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
        self.report({"INFO"}, f"YND exported → {self.filepath}")
        return {"FINISHED"}


class YND_OT_AddVehicleNode(Operator):
    """Adds a vehicle node at the 3D cursor"""
    bl_idname = "gta5_ynd.add_vehicle_node"; bl_label = "Add Vehicle Node"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        n = props.nodes.add()
        n.area_id    = props.area_id
        n.node_id    = _next_free_node_id(props.nodes, n.area_id)
        cursor       = context.scene.cursor.location
        n.position   = (cursor.x, cursor.y, cursor.z)
        # Default vehicle flags: Normal speed, GPS enabled
        _apply_node_flags(n, 2, 0, 0, 64, 134, 2)
        props.node_index   = len(props.nodes) - 1
        _update_ynd_stats(props)
        col = _get_or_create_col(YND_COLLECTION)
        obj = bpy.data.objects.new(f"YND_V_{n.area_id}_{n.node_id}", None)
        obj.empty_display_type = "CUBE"; obj.empty_display_size = 0.5
        obj.location = n.position; obj.lock_rotation = (True,True,True); obj.lock_scale = (True,True,True)
        obj["ynd_type"]="node"; obj["node_index"]=props.node_index
        obj["node_area_id"]=n.area_id; obj["node_id"]=n.node_id
        obj["is_vehicle"]=True; obj["is_freeway"]=False; obj["is_junction"]=False
        _link_obj(obj, col)
        self.report({"INFO"}, f"Vehicle node added: {n.area_id}:{n.node_id}")
        return {"FINISHED"}


class YND_OT_AddPedNode(Operator):
    """Adds a pedestrian node at the 3D cursor"""
    bl_idname = "gta5_ynd.add_ped_node"; bl_label = "Add Pedestrian Node"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        n = props.nodes.add()
        n.area_id  = props.area_id
        n.node_id  = _next_free_node_id(props.nodes, n.area_id)
        cursor     = context.scene.cursor.location
        n.position = (cursor.x, cursor.y, cursor.z)
        # flags1 with special_type PED_CROSSING (value 10 << 3 = 80)
        _apply_node_flags(n, 2, 80, 0, 8, 2, 2)
        props.node_index   = len(props.nodes) - 1
        _update_ynd_stats(props)
        col = _get_or_create_col(YND_COLLECTION)
        obj = bpy.data.objects.new(f"YND_P_{n.area_id}_{n.node_id}", None)
        obj.empty_display_type = "SPHERE"; obj.empty_display_size = 0.3
        obj.location = n.position; obj.lock_rotation = (True,True,True); obj.lock_scale = (True,True,True)
        obj["ynd_type"]="node"; obj["node_index"]=props.node_index
        obj["node_area_id"]=n.area_id; obj["node_id"]=n.node_id
        obj["is_vehicle"]=False; obj["is_freeway"]=False; obj["is_junction"]=False
        _link_obj(obj, col)
        self.report({"INFO"}, f"Pedestrian node added: {n.area_id}:{n.node_id}")
        return {"FINISHED"}


class YND_OT_RemoveNode(Operator):
    """Removes active node and all incoming links from other nodes"""
    bl_idname = "gta5_ynd.remove_node"; bl_label = "Remove Node"
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

        # Remove corresponding node empties to prevent stale sync mappings.
        to_remove = [
            obj for obj in context.scene.objects
            if obj.get("ynd_type") == "node"
            and int(obj.get("node_area_id", -1)) == int(r_area)
            and int(obj.get("node_id", -1)) == int(r_id)
        ]
        for obj in to_remove:
            bpy.data.objects.remove(obj, do_unlink=True)

        # Remove every reference to deleted node from remaining nodes.
        removed_links = _remove_links_targeting_node(props, r_area, r_id)
        props.nodes.remove(idx)
        # Safety pass after removal to catch any stale references.
        removed_links += _remove_links_targeting_node(props, r_area, r_id)
        _prune_invalid_local_links(props)

        # Reindex remaining node empties.
        node_index_map = _build_node_index_map(props.nodes)
        for obj in context.scene.objects:
            if obj.get("ynd_type") != "node":
                continue
            mapped_idx = _find_node_index_for_object(obj, props, node_index_map)
            if mapped_idx >= 0:
                obj["node_index"] = mapped_idx

        props.node_index   = min(idx, len(props.nodes) - 1)
        _update_ynd_stats(props)

        _refresh_ynd_link_objects(props)
        self.report({"INFO"}, f"Node removed: {r_area}:{r_id} ({removed_links} link(s) removed)")
        return {"FINISHED"}


class YND_OT_AddLink(Operator):
    """Adds an outgoing link to the active node"""
    bl_idname = "gta5_ynd.add_link"; bl_label = "Add Link"
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
        _refresh_ynd_link_objects(props)
        return {"FINISHED"}


class YND_OT_RemoveLink(Operator):
    """Removes the active link from the node"""
    bl_idname = "gta5_ynd.remove_link"; bl_label = "Remove Link"
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
        _refresh_ynd_link_objects(props)
        return {"FINISHED"}


class YND_OT_RemoveAllLinks(Operator):
    """Removes ALL links from the active node"""
    bl_idname = "gta5_ynd.remove_all_links"; bl_label = "Remove All Links"
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
        _refresh_ynd_link_objects(props)
        self.report({"INFO"}, f"{count} link(s) removed")
        return {"FINISHED"}


class YND_OT_LinkTwoNodes(Operator):
    """Creates a link from the active node to a target node"""
    bl_idname = "gta5_ynd.link_two_nodes"; bl_label = "Link to Target Node"
    bl_options = {"REGISTER", "UNDO"}
    target_node_id: IntProperty(name="Target Node ID", default=0, min=0)
    target_area_id: IntProperty(name="Target Area ID", default=400, min=0)
    bidirectional:  BoolProperty(name="Bidirectional", default=True)
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
        _refresh_ynd_link_objects(props)
        self.report({"INFO"}, f"Link {'↔' if self.bidirectional else '→'} created, L={dist}")
        return {"FINISHED"}


class YND_OT_GenerateFromCurve(Operator):
    """Generate YND nodes and links from the active Blender curve"""
    bl_idname = "gta5_ynd.generate_from_curve"; bl_label = "Generate from Active Curve"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "CURVE"

    def execute(self, context):
        curve_obj = context.active_object
        props = context.scene.gta5_pathing.ynd
        ok, msg = _populate_ynd_from_curve(
            curve_obj,
            props,
            props.curve_preset,
            bidirectional=props.curve_bidirectional,
        )
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}

        col = _get_or_create_col(YND_COLLECTION)
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        _build_ynd_objects(props, col)

        curve_obj["ynd_type"] = "source_curve"
        curve_obj["ynd_curve_preset"] = props.curve_preset
        curve_obj["ynd_curve_bidirectional"] = props.curve_bidirectional
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class YND_OT_SyncFromCurve(Operator):
    """Rebuild YND nodes and links from the source Blender curve"""
    bl_idname = "gta5_ynd.sync_from_curve"; bl_label = "Sync from Curve"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _find_ynd_source_curve(context) is not None

    def execute(self, context):
        curve_obj = _find_ynd_source_curve(context)
        if curve_obj is None:
            self.report({"WARNING"}, "No YND source curve found.")
            return {"CANCELLED"}

        props = context.scene.gta5_pathing.ynd
        preset_key = curve_obj.get("ynd_curve_preset", props.curve_preset)
        bidirectional = bool(curve_obj.get("ynd_curve_bidirectional", props.curve_bidirectional))
        props.curve_preset = preset_key
        props.curve_bidirectional = bidirectional

        ok, msg = _populate_ynd_from_curve(
            curve_obj,
            props,
            preset_key,
            bidirectional=bidirectional,
            preserve_existing=True,
        )
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}

        col = _get_or_create_col(YND_COLLECTION)
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        _build_ynd_objects(props, col)

        curve_obj["ynd_type"] = "source_curve"
        curve_obj["ynd_curve_preset"] = preset_key
        curve_obj["ynd_curve_bidirectional"] = bidirectional
        self.report({"INFO"}, msg.replace("Generated", "Synced"))
        return {"FINISHED"}


class YND_OT_UpdateLinksFromCurve(Operator):
    """Rebuild only adjacency links from the source curve and preserve manual extras"""
    bl_idname = "gta5_ynd.update_links_from_curve"; bl_label = "Update Links from Curve"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _find_ynd_source_curve(context) is not None

    def execute(self, context):
        curve_obj = _find_ynd_source_curve(context)
        if curve_obj is None:
            self.report({"WARNING"}, "No YND source curve found.")
            return {"CANCELLED"}

        props = context.scene.gta5_pathing.ynd
        preset_key = curve_obj.get("ynd_curve_preset", props.curve_preset)
        bidirectional = bool(curve_obj.get("ynd_curve_bidirectional", props.curve_bidirectional))
        props.curve_preset = preset_key
        props.curve_bidirectional = bidirectional
        ok, msg = _update_curve_links_only(curve_obj, props, preset_key, bidirectional=bidirectional)
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}

        _update_ynd_stats(props)
        _refresh_ynd_link_objects(props)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class YND_OT_SetOneWay(Operator):
    """Make the active node one-way by removing reverse links targeting it"""
    bl_idname = "gta5_ynd.set_one_way"; bl_label = "Set One-Way Links"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        p = context.scene.gta5_pathing.ynd
        return 0 <= p.node_index < len(p.nodes)

    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        node = props.nodes[props.node_index]
        removed = _remove_links_targeting_node(props, node.area_id, node.node_id)
        _refresh_ynd_link_objects(props)
        self.report({"INFO"}, f"{removed} reverse link(s) removed - node is now one-way")
        return {"FINISHED"}


class YND_OT_RecalcLinkLengths(Operator):
    """Recalculate all YND link lengths from current node positions"""
    bl_idname = "gta5_ynd.recalc_link_lengths"; bl_label = "Recalculate Link Lengths"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        recalc = _recalc_all_link_lengths(props)
        _refresh_ynd_link_objects(props)
        self.report({"INFO"}, f"{recalc} link length(s) recalculated")
        return {"FINISHED"}


class YND_OT_ApplyRoadPreset(Operator):
    """Apply the selected YND preset to the active node and its links"""
    bl_idname = "gta5_ynd.apply_road_preset"; bl_label = "Apply Road Preset"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        p = context.scene.gta5_pathing.ynd
        return 0 <= p.node_index < len(p.nodes)

    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        node = props.nodes[props.node_index]
        preset_key = props.curve_preset
        _apply_node_flags(node, *_preset_node_flags(preset_key, 0, 2))
        for link_index, link in enumerate(node.links):
            _apply_link_flags(link, *_preset_link_flags(preset_key, link_index, link_index + 1, max(2, len(node.links) + 1)))
        self.report({"INFO"}, f"Preset '{preset_key}' applied to node {node.area_id}:{node.node_id}")
        return {"FINISHED"}


class YND_OT_SyncFromObjects(Operator):
    """Syncs node positions from Blender empties"""
    bl_idname = "gta5_ynd.sync_from_objects"; bl_label = "Sync from Objects"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        count, stale = _sync_positions_from_node_objects(context, props)
        msg = f"{count} nodes synced"
        if stale:
            msg += f" ({stale} stale object(s) ignored)"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class YND_OT_RepairLocalIds(Operator):
    """Repairs duplicate node IDs in current YND and cleans local invalid links"""
    bl_idname = "gta5_ynd.repair_local_ids"; bl_label = "Repair Local IDs"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.gta5_pathing.ynd
        changed = _repair_duplicate_local_ids(props)
        removed = _prune_invalid_local_links(props)

        # Refresh node object custom properties.
        for obj in context.scene.objects:
            if obj.get("ynd_type") != "node":
                continue
            idx = obj.get("node_index", -1)
            if 0 <= idx < len(props.nodes):
                n = props.nodes[idx]
                obj["node_area_id"] = n.area_id
                obj["node_id"] = n.node_id

        _refresh_ynd_link_objects(props)

        msg = f"Repair done: {changed} duplicate ID(s) fixed, {removed} local invalid link(s) removed"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


_classes = [
    YND_OT_Import, YND_OT_Export,
    YND_OT_AddVehicleNode, YND_OT_AddPedNode, YND_OT_RemoveNode,
    YND_OT_AddLink, YND_OT_RemoveLink, YND_OT_RemoveAllLinks,
    YND_OT_LinkTwoNodes, YND_OT_GenerateFromCurve, YND_OT_SyncFromCurve, YND_OT_UpdateLinksFromCurve, YND_OT_SetOneWay,
    YND_OT_RecalcLinkLengths, YND_OT_ApplyRoadPreset, YND_OT_SyncFromObjects, YND_OT_RepairLocalIds,
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
