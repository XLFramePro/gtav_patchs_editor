import bpy
import math
from mathutils import Vector

from .constants import YND_COLLECTION, YND_CURVE_PRESETS
from .io import (
    _apply_link_flags,
    _apply_node_flags,
    _link_flags_to_ints,
    _node_flags_to_ints,
    _node_is_junction,
    _node_is_vehicle,
    _update_ynd_stats,
)


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


def _find_node_by_area_id(nodes, area_id, node_id):
    for i, n in enumerate(nodes):
        if n.area_id == area_id and n.node_id == node_id:
            return i, n
    return None, None


def _next_free_node_id(nodes, area_id):
    """Return next new node_id for an area without reusing freed IDs.

    Patch workflow safety: avoid ID reuse because neighboring YND files can
    still reference historical node IDs in this area.
    """
    used = [int(n.node_id) for n in nodes if int(n.area_id) == int(area_id)]
    if not used:
        return 0
    return max(used) + 1


def _build_node_index_map(nodes):
    """Map (area_id, node_id, is_vehicle) -> node index for stable syncing."""
    index_map = {}
    for i, n in enumerate(nodes):
        index_map[(int(n.area_id), int(n.node_id), 1 if _node_is_vehicle(n) else 0)] = i
    return index_map


def _calc_area_id_from_position(position):
    """Convert world XY to GTA V YND area index on the 32x32 grid."""
    x, y = float(position[0]), float(position[1])
    cell_x = max(0, min(31, int(math.floor((x + 8192.0) / 512.0))))
    cell_y = max(0, min(31, int(math.floor((y + 8192.0) / 512.0))))
    return (cell_y * 32) + cell_x


def _node_is_freeway(n):
    return n.flags2.freeway


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
        key = (
            (chain_index, point_index)
            if chain_index >= 0 and point_index >= 0
            else ("flat", fallback_index)
        )
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
                if target_key is None:
                    # Non-curve node: preserve using stable (area_id, node_id) key.
                    target_key = ("node", int(target.area_id), int(target.node_id))
                node_state["extra_links"].append(
                    {
                        "target_key": target_key,
                        "flags": _link_flags_to_ints(link),
                        "length": int(link.link_length),
                    }
                )
                continue

            node_state["links"][relation] = {
                "flags": _link_flags_to_ints(link),
            }

        snapshot[key] = node_state

    return snapshot


def _next_preserved_or_free_node_id(snapshot_state, used_by_area, area_id):
    """Reuse previous node_id when possible, otherwise allocate next new ID."""
    used = used_by_area.setdefault(int(area_id), set())
    if snapshot_state is not None and int(snapshot_state["area_id"]) == int(area_id):
        old_id = int(snapshot_state["node_id"])
        if old_id not in used:
            used.add(old_id)
            return old_id

    node_id = (max(used) + 1) if used else 0
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


def _populate_ynd_from_curve(curve_obj, props, preset_key, bidirectional=True, preserve_existing=False, append_mode=False):
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

    if append_mode:
        indices_to_remove = [i for i, n in enumerate(props.nodes) if n.curve_chain_index >= 0]
        for i in reversed(indices_to_remove):
            props.nodes.remove(i)
        used_ids_by_area = {}
        for n in props.nodes:
            used_ids_by_area.setdefault(int(n.area_id), set()).add(int(n.node_id))
    else:
        props.nodes.clear()
        used_ids_by_area = {}

    created = []
    created_by_key = {}
    first_area_id = None

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
                tk = tuple(extra_link["target_key"])
                if tk[0] == "node":
                    _, target = _find_node_by_area_id(props.nodes, tk[1], tk[2])
                else:
                    target = created_by_key.get(tk)
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
                link.link_length = int(
                    min(255, max(1.0, (Vector(node.position) - Vector(target.position)).length))
                )
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
                tk = tuple(extra_link["target_key"])
                if tk[0] == "node":
                    _, target = _find_node_by_area_id(props.nodes, tk[1], tk[2])
                else:
                    target = tracked_nodes.get(tk)
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
    is_vehicle = obj.get("is_vehicle")
    if area is not None and node_id is not None and is_vehicle is not None:
        idx = node_index_map.get((int(area), int(node_id), 1 if bool(is_vehicle) else 0))
        if idx is not None:
            return idx

    idx = obj.get("node_index", -1)
    if 0 <= idx < len(props.nodes):
        n = props.nodes[idx]
        if area is None or node_id is None:
            return idx
        if int(n.area_id) == int(area) and int(n.node_id) == int(node_id):
            if is_vehicle is None or (1 if _node_is_vehicle(n) else 0) == (1 if bool(is_vehicle) else 0):
                return idx

    if area is not None and node_id is not None and is_vehicle is None:
        for i, n in enumerate(props.nodes):
            if int(n.area_id) == int(area) and int(n.node_id) == int(node_id):
                return i

    return -1


def _sync_positions_from_node_objects(context, props):
    """Sync node positions from empties using stable identifiers.

    Returns (synced_count, stale_count).
    """
    node_index_map = _build_node_index_map(props.nodes)
    synced = 0
    stale = 0

    col = bpy.data.collections.get(YND_COLLECTION)
    objects = col.objects if col is not None else context.scene.objects

    for obj in objects:
        if obj.get("ynd_type") != "node":
            continue

        idx = _find_node_index_for_object(obj, props, node_index_map)
        if idx < 0:
            stale += 1
            continue

        node = props.nodes[idx]
        node.position = tuple(obj.location)

        obj["node_index"] = idx
        obj["node_area_id"] = node.area_id
        obj["node_id"] = node.node_id
        obj["is_vehicle"] = bool(_node_is_vehicle(node))
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
            i
            for i, lk in enumerate(n.links)
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
            i
            for i, lk in enumerate(n.links)
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
            obj = bpy.data.objects.new(
                f"YND_Link_{node.area_id}_{node.node_id}_{lk.to_area_id}_{lk.to_node_id}",
                curve_data,
            )
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
            None,
        )
        obj.empty_display_type = "CUBE" if is_veh else "SPHERE"
        obj.empty_display_size = 0.5 if is_veh else 0.3
        obj.location = node.position
        obj.lock_rotation = (True, True, True)
        obj.lock_scale = (True, True, True)
        obj["ynd_type"] = "node"
        obj["node_index"] = i
        obj["node_area_id"] = node.area_id
        obj["node_id"] = node.node_id
        obj["street_name"] = node.street_name
        obj["is_vehicle"] = is_veh
        obj["is_freeway"] = _node_is_freeway(node)
        obj["is_junction"] = _node_is_junction(node)
        obj.parent = root_obj
        _link_obj(obj, col)

    links_root = _build_ynd_link_objects(props, col)
    links_root.parent = root_obj
    return root_obj
