"""props.py — Tous les PropertyGroups. Un seul endroit de vérité."""
import bpy
from bpy.props import (BoolProperty, IntProperty, FloatProperty, StringProperty,
                       EnumProperty, FloatVectorProperty, CollectionProperty, PointerProperty)
from bpy.types import PropertyGroup


# ═══════════════════════════════════════════════════════════════════════════════
#  CONSTANTES PARTAGÉES
# ═══════════════════════════════════════════════════════════════════════════════

# All GTA5 scenario point flags
SCENARIO_FLAGS = [
    "NoSpawn", "PreciseUseTime", "PreciseUseTimePM",
    "EventsInRadiusTriggerThreatResponse", "EventsInRadiusTriggerDisputes",
    "HighPriority", "IgnoreMaxInRange", "EndScenarioIfPlayerWithinRadius",
    "TerritorialScenario", "StationaryReactions", "ActivateVehicleSiren",
    "OpenDoor", "InVehicleSeat", "AbortScenariosOnSuicide",
]

# All GTA5 train track point flags  
TRAIN_FLAGS_LIST = [
    (0, "Normal"),
    (1, "Boost"),
    (4, "Switch/Junction"),
    (5, "Boost + Switch"),
]

PED_SPECIAL_TYPES = {"PED_CROSSING", "PED_ASSISTED", "PED_NOWAIT"}

SPEED_ITEMS = [
    ("SLOW",   "Slow",   "", 0), ("NORMAL", "Normal", "", 1),
    ("FAST",   "Fast",   "", 2), ("FASTER", "Faster", "", 3),
]

YND_SPECIAL_ITEMS = [
    ("NONE",          "None",                       "", 0),
    ("PARKING",       "Parking Space",              "", 1),
    ("PED_CROSSING",  "Ped Road Crossing",          "", 2),
    ("PED_ASSISTED",  "Ped Assisted Movement",      "", 3),
    ("TRAFFIC_LIGHT", "Traffic Light Junction Stop","", 4),
    ("STOP_SIGN",     "Stop Sign",                  "", 5),
    ("CAUTION",       "Caution",                    "", 6),
    ("PED_NOWAIT",    "Ped Road Crossing No Wait",  "", 7),
    ("EMERGENCY",     "Emergency Vehicles Only",    "", 8),
    ("OFFROAD_JCT",   "Offroad Junction",           "", 9),
]

SPEC_TO_INT = {"NONE":0,"PARKING":2,"PED_CROSSING":10,"PED_ASSISTED":14,
               "TRAFFIC_LIGHT":15,"STOP_SIGN":16,"CAUTION":17,"PED_NOWAIT":18,
               "EMERGENCY":19,"OFFROAD_JCT":20}
INT_TO_SPEC = {v: k for k, v in SPEC_TO_INT.items()}

AVAIL_ITEMS = [
    ("0","None",""),("1","SP Only",""),("2","MP Only",""),("3","SP + MP","")
]

ITYPE_NAMES = {
    0:"Drinking",    1:"Sitting",       2:"CopWandering",  3:"Waiter",
    4:"MobilePhone", 5:"Loitering",     6:"Security",      7:"Smoking",
    8:"WatchWorld",  9:"WatchRoad",    10:"Prostitute",   11:"InVehicle",
   12:"GuardStand", 13:"WatchTraffic", 14:"Clipboard",    15:"CardboardBox",
   16:"WaitForBus", 17:"BeachBum",     18:"FishingRiv",   19:"Sunbathe",
   20:"WatchBoats", 21:"BusStopper",   22:"Tennis",       23:"Paparazzi",
   24:"AnimalSeat", 25:"Yoga",         26:"DriveBy",      27:"PoliceBike",
   28:"Busker",     29:"Leaning",      30:"ATM",
}

YNV_PRESET_ITEMS = [
    ("ROAD","Route",""),("PAVEMENT","Trottoir",""),("INTERIOR","Intérieur",""),
    ("WATER","Eau",""),("SHALLOW","Eau peu prof.",""),("TRAIN","Voie ferrée",""),
    ("COVER","Cover",""),("SPAWN","Zone spawn",""),("CUSTOM","Custom",""),
]
# b0,b1,b2,b3 par défaut pour chaque préset
# Valeurs b0,b1,b2,b3 calqués sur la référence navmesh_material.py (CodeWalker 30_dev47)
# audio_reverb_size/wet = 0 par défaut pour tous les présets
YNV_PRESET_VALUES = {
    # f0       f1  f2    f3
    "ROAD"    :(0,   0,  2,   0),   # IsRoad
    "PAVEMENT":(4,   0,  0,   0),   # IsPavement
    "INTERIOR":(0,  64,  0,   0),   # IsInterior  (bit6 de b1)
    "WATER"   :(128, 0,  0,   0),   # IsWater
    "SHALLOW" :(0,   0, 16,   0),   # IsShallowWater
    "TRAIN"   :(0,   0,  8,   0),   # IsTrainTrack
    "COVER"   :(0,   0,  2,  63),   # IsRoad + Cover 6 dirs
    "SPAWN"   :(0,   0,  3,   0),   # IsNetworkSpawnCandidate + IsRoad
    "CUSTOM"  :(0,   0,  0,   0),
}

NAV_POINT_TYPES = [("0","None",""),("1","Type 1",""),("2","Cover",""),
                   ("3","Ladder",""),("4","Door",""),("5","Type 5","")]


# ═══════════════════════════════════════════════════════════════════════════════
#  YNV
# ═══════════════════════════════════════════════════════════════════════════════

class YNV_PolyFlags(PropertyGroup):
    """Flags navmesh (structure exacte CodeWalker 30_dev47 + Sollumz ref)."""
    # Byte 0 — Surface
    is_small:          BoolProperty(name="Is Small (auto)",         description="Auto-calculé: aire < 2.0m²")
    is_large:          BoolProperty(name="Is Large (auto)",         description="Auto-calculé: aire > 40.0m²")
    is_pavement:       BoolProperty(name="Is Pavement")
    is_in_shelter:     BoolProperty(name="Is In Shelter",           description="Sous abri / underground")
    unused_b0_4:       BoolProperty(name="Unused b0.4")
    unused_b0_5:       BoolProperty(name="Unused b0.5")
    is_too_steep:      BoolProperty(name="Too Steep To Walk On")
    is_water:          BoolProperty(name="Is Water")
    # Byte 1 — Audio + Props
    audio_reverb_size: IntProperty(name="Audio Reverb Size",        min=0, max=3)
    audio_reverb_wet:  IntProperty(name="Audio Reverb Wet",         min=0, max=3)
    unused_b1_4:       BoolProperty(name="Unused b1.4")
    is_near_car_node:  BoolProperty(name="Is Near Car Node")
    is_interior:       BoolProperty(name="Is Interior")
    is_isolated:       BoolProperty(name="Is Isolated")
    # Byte 2 — Comportement
    is_network_spawn:  BoolProperty(name="Network Spawn Candidate")
    is_road:           BoolProperty(name="Is Road")
    lies_along_edge:   BoolProperty(name="Lies Along Edge")
    is_train_track:    BoolProperty(name="Is Train Track")
    is_shallow_water:  BoolProperty(name="Is Shallow Water")
    ped_density:       IntProperty(name="Ped Density",              min=0, max=7)
    # Byte 3 — Cover directions
    cover_dir0: BoolProperty(name="+Y");    cover_dir1: BoolProperty(name="-X+Y")
    cover_dir2: BoolProperty(name="-X");    cover_dir3: BoolProperty(name="-X-Y")
    cover_dir4: BoolProperty(name="-Y");    cover_dir5: BoolProperty(name="+X-Y")
    cover_dir6: BoolProperty(name="+X");    cover_dir7: BoolProperty(name="+X+Y")
    # Byte 4 — DLC
    is_dlc_stitch: BoolProperty(name="Is DLC Stitch Poly")

    def to_str(self) -> str:
        b0=(int(self.is_small)<<0)|(int(self.is_large)<<1)|(int(self.is_pavement)<<2)|\
           (int(self.is_in_shelter)<<3)|(int(self.unused_b0_4)<<4)|(int(self.unused_b0_5)<<5)|\
           (int(self.is_too_steep)<<6)|(int(self.is_water)<<7)
        b1=(self.audio_reverb_size&3)|((self.audio_reverb_wet&3)<<2)|(int(self.unused_b1_4)<<4)|\
           (int(self.is_near_car_node)<<5)|(int(self.is_interior)<<6)|(int(self.is_isolated)<<7)
        b2=(int(self.is_network_spawn)<<0)|(int(self.is_road)<<1)|(int(self.lies_along_edge)<<2)|\
           (int(self.is_train_track)<<3)|(int(self.is_shallow_water)<<4)|((self.ped_density&7)<<5)
        b3=(int(self.cover_dir0)<<0)|(int(self.cover_dir1)<<1)|(int(self.cover_dir2)<<2)|\
           (int(self.cover_dir3)<<3)|(int(self.cover_dir4)<<4)|(int(self.cover_dir5)<<5)|\
           (int(self.cover_dir6)<<6)|(int(self.cover_dir7)<<7)
        f4=int(self.is_dlc_stitch)
        return f"{b0} {b1} {b2} {b3} 0 0 {f4}"

    def from_str(self, s: str):
        try: p=[int(x) for x in s.split()]
        except: return
        while len(p)<7: p.append(0)
        b0,b1,b2,b3,f4=p[0],p[1],p[2],p[3],p[6]
        self.is_small=(b0>>0)&1; self.is_large=(b0>>1)&1; self.is_pavement=(b0>>2)&1
        self.is_in_shelter=(b0>>3)&1; self.unused_b0_4=(b0>>4)&1; self.unused_b0_5=(b0>>5)&1
        self.is_too_steep=(b0>>6)&1; self.is_water=(b0>>7)&1
        self.audio_reverb_size=b1&3; self.audio_reverb_wet=(b1>>2)&3
        self.unused_b1_4=(b1>>4)&1; self.is_near_car_node=(b1>>5)&1
        self.is_interior=(b1>>6)&1; self.is_isolated=(b1>>7)&1
        self.is_network_spawn=(b2>>0)&1; self.is_road=(b2>>1)&1; self.lies_along_edge=(b2>>2)&1
        self.is_train_track=(b2>>3)&1; self.is_shallow_water=(b2>>4)&1; self.ped_density=(b2>>5)&7
        self.cover_dir0=(b3>>0)&1; self.cover_dir1=(b3>>1)&1; self.cover_dir2=(b3>>2)&1
        self.cover_dir3=(b3>>3)&1; self.cover_dir4=(b3>>4)&1; self.cover_dir5=(b3>>5)&1
        self.cover_dir6=(b3>>6)&1; self.cover_dir7=(b3>>7)&1
        self.is_dlc_stitch=bool(f4&1)

    def from_preset(self, preset: str):
        b=YNV_PRESET_VALUES.get(preset,(0,0,0,0))
        self.from_str(f"{b[0]} {b[1]} {b[2]} {b[3]} 0 0 0")


class YNV_Portal(PropertyGroup):
    portal_type: IntProperty(name="Type",      default=1, min=1, max=3)
    angle:       FloatProperty(name="Angle",   default=0.0, subtype="ANGLE")
    poly_from:   IntProperty(name="Poly From", default=0, min=0)
    poly_to:     IntProperty(name="Poly To",   default=0, min=0)
    pos_from:    FloatVectorProperty(name="Pos From", size=3, subtype="XYZ", default=(0,0,0))
    pos_to:      FloatVectorProperty(name="Pos To",   size=3, subtype="XYZ", default=(0,0,0))


class YNV_NavPoint(PropertyGroup):
    point_type: EnumProperty(name="Type", items=NAV_POINT_TYPES, default="0")
    angle:      FloatProperty(name="Angle", default=0.0, subtype="ANGLE")
    position:   FloatVectorProperty(name="Position", size=3, subtype="XYZ", default=(0,0,0))


class YNV_Props(PropertyGroup):
    filepath:      StringProperty(name="Fichier", subtype="FILE_PATH")
    area_id:       IntProperty(name="Area ID", default=0, min=0)
    content_flags: StringProperty(name="Content Flags", default="Polygons, Portals")
    bb_min:        FloatVectorProperty(name="BB Min", size=3, subtype="XYZ", default=(0,0,0))
    bb_max:        FloatVectorProperty(name="BB Max", size=3, subtype="XYZ", default=(0,0,0))
    portals:       CollectionProperty(type=YNV_Portal)
    portal_idx:    IntProperty(default=-1)
    nav_points:    CollectionProperty(type=YNV_NavPoint)
    navpt_idx:     IntProperty(default=-1)
    edit_flags:    PointerProperty(type=YNV_PolyFlags)
    flag_preset:   EnumProperty(name="Préset", items=YNV_PRESET_ITEMS, default="ROAD")
    # Mesh Cutter
    tile_size:     FloatProperty(name="Tile Size", default=150.0, min=10.0)
    tile_offset_x: FloatProperty(name="Offset X",  default=0.0)
    tile_offset_y: FloatProperty(name="Offset Y",  default=0.0)
    # Affichage
    show_bb:       BoolProperty(name="Bounding Box", default=True)
    show_portals:  BoolProperty(name="Portails",     default=True)
    show_navpts:   BoolProperty(name="Nav Points",   default=True)
    # Stats
    stat_polys:    IntProperty(default=0)
    stat_portals:  IntProperty(default=0)
    stat_navpts:   IntProperty(default=0)
    stat_mats:     IntProperty(default=0)


# ═══════════════════════════════════════════════════════════════════════════════
#  YND — FLAGS NOEUDS
# ═══════════════════════════════════════════════════════════════════════════════

class YND_NF0(PropertyGroup):
    """Flags0 — Navigation de base"""
    scripted:        BoolProperty(name="Scripted")
    gps_enabled:     BoolProperty(name="GPS Enabled")
    unused_4:        BoolProperty(name="Unused 4")
    offroad:         BoolProperty(name="Offroad")
    unused_16:       BoolProperty(name="Unused 16")
    no_big_vehicles: BoolProperty(name="No Big Vehicles")
    cannot_go_right: BoolProperty(name="Cannot Go Right")
    cannot_go_left:  BoolProperty(name="Cannot Go Left")
    def to_int(self):
        return(self.scripted<<0)|(self.gps_enabled<<1)|(self.unused_4<<2)|(self.offroad<<3)|\
              (self.unused_16<<4)|(self.no_big_vehicles<<5)|(self.cannot_go_right<<6)|(self.cannot_go_left<<7)
    def from_int(self,v):
        self.scripted=(v>>0)&1; self.gps_enabled=(v>>1)&1; self.unused_4=(v>>2)&1
        self.offroad=(v>>3)&1; self.unused_16=(v>>4)&1; self.no_big_vehicles=(v>>5)&1
        self.cannot_go_right=(v>>6)&1; self.cannot_go_left=(v>>7)&1


class YND_NF1(PropertyGroup):
    """Flags1 — Type spécial"""
    slip_lane:           BoolProperty(name="Slip Lane")
    indicate_keep_left:  BoolProperty(name="Indicate Keep Left")
    indicate_keep_right: BoolProperty(name="Indicate Keep Right")
    special_type:        EnumProperty(items=YND_SPECIAL_ITEMS, name="Special Type", default="NONE")
    def to_int(self):
        return(self.slip_lane<<0)|(self.indicate_keep_left<<1)|(self.indicate_keep_right<<2)|\
              (SPEC_TO_INT.get(self.special_type,0)<<3)
    def from_int(self,v):
        self.slip_lane=(v>>0)&1; self.indicate_keep_left=(v>>1)&1; self.indicate_keep_right=(v>>2)&1
        self.special_type=INT_TO_SPEC.get(v>>3,"NONE")


class YND_NF2(PropertyGroup):
    """Flags2 — Zone / Réseau"""
    no_gps:      BoolProperty(name="No GPS")
    unused_2:    BoolProperty(name="Unused 2")
    junction:    BoolProperty(name="Junction")
    unused_8:    BoolProperty(name="Unused 8")
    disabled_1:  BoolProperty(name="Disabled 1")
    water_boats: BoolProperty(name="Water / Boats")
    freeway:     BoolProperty(name="Freeway")
    disabled_2:  BoolProperty(name="Disabled 2")
    def to_int(self):
        return(self.no_gps<<0)|(self.unused_2<<1)|(self.junction<<2)|(self.unused_8<<3)|\
              (self.disabled_1<<4)|(self.water_boats<<5)|(self.freeway<<6)|(self.disabled_2<<7)
    def from_int(self,v):
        self.no_gps=(v>>0)&1; self.unused_2=(v>>1)&1; self.junction=(v>>2)&1
        self.unused_8=(v>>3)&1; self.disabled_1=(v>>4)&1; self.water_boats=(v>>5)&1
        self.freeway=(v>>6)&1; self.disabled_2=(v>>7)&1


class YND_NF3(PropertyGroup):
    """Flags3 — Tunnel / Heuristique"""
    tunnel:    BoolProperty(name="Tunnel")
    heuristic: IntProperty(name="Heuristic", min=0, max=127)
    def to_int(self): return int(self.tunnel)|(self.heuristic<<1)
    def from_int(self,v): self.tunnel=bool(v&1); self.heuristic=(v>>1)&127


class YND_NF4(PropertyGroup):
    """Flags4 — Densité / Dead-end"""
    density:        IntProperty(name="Density",     min=0, max=15)
    deadendness:    IntProperty(name="Deadendness", min=0, max=7)
    left_turn_only: BoolProperty(name="Left Turn Only")
    def to_int(self): return(self.density&0xF)|((self.deadendness&7)<<4)|(int(self.left_turn_only)<<7)
    def from_int(self,v): self.density=v&0xF; self.deadendness=(v>>4)&7; self.left_turn_only=bool(v&128)


class YND_NF5(PropertyGroup):
    """Flags5 — Vitesse / Heightmap"""
    has_junction_heightmap: BoolProperty(name="Has Junction Heightmap")
    speed: EnumProperty(items=SPEED_ITEMS, name="Speed", default="NORMAL")
    def to_int(self): return int(self.has_junction_heightmap)|{"SLOW":0,"NORMAL":2,"FAST":4,"FASTER":6}.get(self.speed,0)
    def from_int(self,v):
        self.has_junction_heightmap=bool(v&1)
        self.speed={0:"SLOW",2:"NORMAL",4:"FAST",6:"FASTER"}.get(v&0xFE,"NORMAL")


# ── Flags Lien ────────────────────────────────────────────────────────────────

class YND_LF0(PropertyGroup):
    """LinkFlags0 — GPS"""
    gps_both_ways:     BoolProperty(name="GPS Both Ways")
    block_if_no_lanes: BoolProperty(name="Block If No Lanes")
    unknown_1:         IntProperty(name="Unknown 1", min=0, max=7)
    unknown_2:         IntProperty(name="Unknown 2", min=0, max=7)
    def to_int(self): return int(self.gps_both_ways)|(int(self.block_if_no_lanes)<<1)|((self.unknown_1&7)<<2)|((self.unknown_2&7)<<5)
    def from_int(self,v): self.gps_both_ways=(v>>0)&1; self.block_if_no_lanes=(v>>1)&1; self.unknown_1=(v>>2)&7; self.unknown_2=(v>>5)&7


class YND_LF1(PropertyGroup):
    """LinkFlags1 — Route"""
    unused_1:        BoolProperty(name="Unused 1")
    narrow_road:     BoolProperty(name="Narrow Road")
    dead_end:        BoolProperty(name="Dead End")
    dead_end_exit:   BoolProperty(name="Dead End Exit")
    negative_offset: BoolProperty(name="Negative Offset")
    offset:          IntProperty(name="Offset", min=0, max=7)
    def to_int(self): return int(self.unused_1)|(int(self.narrow_road)<<1)|(int(self.dead_end)<<2)|(int(self.dead_end_exit)<<3)|((self.offset&7)<<4)|(int(self.negative_offset)<<7)
    def from_int(self,v): self.unused_1=(v>>0)&1; self.narrow_road=(v>>1)&1; self.dead_end=(v>>2)&1; self.dead_end_exit=(v>>3)&1; self.offset=(v>>4)&7; self.negative_offset=(v>>7)&1


class YND_LF2(PropertyGroup):
    """LinkFlags2 — Voies"""
    dont_use_for_navigation: BoolProperty(name="Don't Use For Navigation")
    shortcut:      BoolProperty(name="Shortcut")
    back_lanes:    IntProperty(name="Back Lanes",    min=0, max=7)
    forward_lanes: IntProperty(name="Forward Lanes", min=0, max=7)
    def to_int(self): return int(self.dont_use_for_navigation)|(int(self.shortcut)<<1)|((self.back_lanes&7)<<2)|((self.forward_lanes&7)<<5)
    def from_int(self,v): self.dont_use_for_navigation=(v>>0)&1; self.shortcut=(v>>1)&1; self.back_lanes=(v>>2)&7; self.forward_lanes=(v>>5)&7


class YND_Junction(PropertyGroup):
    """Données d'un carrefour avec heightmap encodée en hex."""
    # String-based pour préserver le format original exactement
    pos_x:    StringProperty(name="Pos X", default="0")
    pos_y:    StringProperty(name="Pos Y", default="0")
    min_z:    StringProperty(name="Min Z", default="0")
    max_z:    StringProperty(name="Max Z", default="0")
    size_x:   StringProperty(name="Size X", default="8")
    size_y:   StringProperty(name="Size Y", default="8")
    heightmap: StringProperty(name="Heightmap", default="")


class YND_JunctionRef(PropertyGroup):
    """Référence noeud → junction (liaison du graphe)."""
    area_id:     IntProperty(name="Area ID",     default=400, min=0)
    node_id:     IntProperty(name="Node ID",     default=0,   min=0)
    junction_id: IntProperty(name="Junction ID", default=0,   min=0)
    unk0:        IntProperty(name="Unk0",         default=0,   min=0)


class YND_Link(PropertyGroup):
    to_area_id:  IntProperty(name="To Area", default=0, min=0)
    to_node_id:  IntProperty(name="To Node", default=0, min=0)
    lf0:         PointerProperty(type=YND_LF0)
    lf1:         PointerProperty(type=YND_LF1)
    lf2:         PointerProperty(type=YND_LF2)
    link_length: IntProperty(name="Longueur", default=10, min=1, max=255)


class YND_Node(PropertyGroup):
    area_id:     IntProperty(name="Area ID",   default=400, min=0)
    node_id:     IntProperty(name="Node ID",   default=0,   min=0)
    street_name: StringProperty(name="Rue",    default="")
    position:    FloatVectorProperty(name="Position", size=3, subtype="XYZ", default=(0,0,0))
    pos_x_str:   StringProperty(default="")
    pos_y_str:   StringProperty(default="")
    pos_z_str:   StringProperty(default="")
    nf0: PointerProperty(type=YND_NF0)
    nf1: PointerProperty(type=YND_NF1)
    nf2: PointerProperty(type=YND_NF2)
    nf3: PointerProperty(type=YND_NF3)
    nf4: PointerProperty(type=YND_NF4)
    nf5: PointerProperty(type=YND_NF5)
    junction:  PointerProperty(type=YND_Junction)
    links:     CollectionProperty(type=YND_Link)
    link_idx:  IntProperty(default=-1)

    @property
    def is_vehicle(self) -> bool: return self.nf1.special_type not in PED_SPECIAL_TYPES
    @property
    def is_freeway(self) -> bool: return bool(self.nf2.freeway)
    @property
    def is_junction(self) -> bool: return bool(self.nf2.junction)


class YND_JunctionRef(PropertyGroup):
    area_id:    IntProperty(name="Area ID",    default=0)
    node_id:    IntProperty(name="Node ID",    default=0)
    junction_id:IntProperty(name="Junction ID",default=0)
    unk0:       IntProperty(name="Unk0",       default=0)


class YND_Props(PropertyGroup):
    filepath:  StringProperty(name="Fichier", subtype="FILE_PATH")
    area_id:   IntProperty(name="Area ID", default=400, min=0)
    nodes:         CollectionProperty(type=YND_Node)
    node_idx:      IntProperty(default=-1)
    junctions:     CollectionProperty(type=YND_Junction)
    junction_refs: CollectionProperty(type=YND_JunctionRef)
    # Affichage
    show_vehicle:   BoolProperty(name="Véhicules",   default=True)
    show_ped:       BoolProperty(name="Piétons",     default=True)
    show_links:     BoolProperty(name="Liens",       default=True)
    show_junctions: BoolProperty(name="Carrefours",  default=True)
    filter_street:  StringProperty(name="Filtrer rue")
    # Stats
    stat_total:   IntProperty(default=0)
    stat_vehicle: IntProperty(default=0)
    stat_ped:     IntProperty(default=0)
    stat_jct:     IntProperty(default=0)


# ═══════════════════════════════════════════════════════════════════════════════
#  YMT
# ═══════════════════════════════════════════════════════════════════════════════

class YMT_ScenarioPoint(PropertyGroup):
    itype:            IntProperty(name="iType",            default=1,   min=0, max=255)
    model_set_id:     IntProperty(name="ModelSet ID",      default=0,   min=0)
    interior_id:      IntProperty(name="Interior ID",      default=0,   min=0)
    imap_id:          IntProperty(name="IMap ID",          default=0,   min=0)
    probability:      IntProperty(name="Probabilité",      default=0,   min=0, max=255)
    avail_mp_sp:      IntProperty(name="MP/SP",            default=3,   min=0, max=3)
    time_start:       IntProperty(name="Heure début",      default=0,   min=0, max=23)
    time_end:         IntProperty(name="Heure fin",        default=24,  min=0, max=24)
    radius:           IntProperty(name="Rayon",            default=0,   min=0)
    time_till_leaves: IntProperty(name="Tps avant départ", default=255, min=0, max=255)
    scenario_group:   IntProperty(name="Groupe",           default=0,   min=0)
    flags:            StringProperty(name="Flags",         default="")
    position:         FloatVectorProperty(name="Pos+Direction", size=4, default=(0,0,0,0))


class YMT_ChainingNode(PropertyGroup):
    position:      FloatVectorProperty(name="Position", size=3, subtype="XYZ", default=(0,0,0))
    scenario_type: StringProperty(name="Scénario type", default="standing")
    hash_9b:       StringProperty(name="hash_9B1D60AB",  default="")
    has_incoming:  BoolProperty(name="Has Incoming")
    has_outgoing:  BoolProperty(name="Has Outgoing", default=True)


class YMT_ChainingEdge(PropertyGroup):
    node_from: IntProperty(name="De",        default=0, min=0)
    node_to:   IntProperty(name="À",         default=0, min=0)
    action:    IntProperty(name="Action",     default=0, min=0)
    nav_mode:  IntProperty(name="Nav Mode",   default=1, min=0, max=3)
    nav_speed: IntProperty(name="Nav Speed",  default=2, min=0, max=3)


class YMT_Chain(PropertyGroup):
    hash_name: StringProperty(name="Hash ID",  default="1")
    edge_ids:  StringProperty(name="Edge IDs", default="")


class YMT_EntityOverride(PropertyGroup):
    entity_type:     StringProperty(name="Entity Type",    default="")
    entity_position: FloatVectorProperty(name="Position",  size=3, subtype="XYZ", default=(0,0,0))
    may_not_exist:   BoolProperty(name="May Not Exist",     default=True)
    prevent_art:     BoolProperty(name="Prevent Art Points",default=False)


class YMT_Cluster(PropertyGroup):
    center_x:    FloatProperty(name="Center X", default=0.0)
    center_y:    FloatProperty(name="Center Y", default=0.0)
    center_z:    FloatProperty(name="Center Z", default=0.0)
    radius:      FloatProperty(name="Radius",   default=1.0, min=0.0)
    hash_4151:   IntProperty(name="hash_4151BB75", default=0)
    hash_ba87:   BoolProperty(name="hash_BA87159C", default=False)


class YMT_Props(PropertyGroup):
    filepath:       StringProperty(name="Fichier", subtype="FILE_PATH")
    version_number: IntProperty(name="Version",    default=80, min=0)
    # Scenario Points
    points:    CollectionProperty(type=YMT_ScenarioPoint)
    point_idx: IntProperty(default=-1)
    # Chaining Graph
    chain_nodes: CollectionProperty(type=YMT_ChainingNode)
    cn_idx:      IntProperty(default=-1)
    chain_edges: CollectionProperty(type=YMT_ChainingEdge)
    ce_idx:      IntProperty(default=-1)
    chains:      CollectionProperty(type=YMT_Chain)
    chain_idx:   IntProperty(default=-1)
    # Entity Overrides
    entity_overrides: CollectionProperty(type=YMT_EntityOverride)
    eo_idx:           IntProperty(default=-1)
    # Clusters
    clusters:    CollectionProperty(type=YMT_Cluster)
    cluster_idx: IntProperty(default=-1)
    # AccelGrid
    ag_min_cell_x: IntProperty(name="Min Cell X", default=-4)
    ag_max_cell_x: IntProperty(name="Max Cell X", default=5)
    ag_min_cell_y: IntProperty(name="Min Cell Y", default=-64)
    ag_max_cell_y: IntProperty(name="Max Cell Y", default=-48)
    ag_cell_dim_x: IntProperty(name="Dim Cell X", default=32)
    ag_cell_dim_y: IntProperty(name="Dim Cell Y", default=32)
    # LookUps (une ligne par nom, séparées par \n)
    lu_type_names:    StringProperty(default="standing")
    lu_ped_models:    StringProperty(default="none")
    lu_veh_models:    StringProperty(default="none")
    lu_group_names:   StringProperty(default="none")
    lu_interior_names:StringProperty(default="none")
    lu_imap_names:    StringProperty(default="none")
    # Affichage
    show_points: BoolProperty(name="Points",   default=True)
    show_chain:  BoolProperty(name="Chaînage", default=True)
    filter_itype:IntProperty(name="Filtrer iType (-1=tous)", default=-1, min=-1, max=255)
    # Stats
    stat_points: IntProperty(default=0)
    stat_cn:     IntProperty(default=0)
    stat_ce:     IntProperty(default=0)
    stat_chains: IntProperty(default=0)


# ═══════════════════════════════════════════════════════════════════════════════
#  TRAINS
# ═══════════════════════════════════════════════════════════════════════════════

class TRAINS_Point(PropertyGroup):
    position: FloatVectorProperty(name="Position", size=3, subtype="XYZ", default=(0,0,0))
    flag:     IntProperty(name="Flag", default=0, min=0, max=5,
                          description="0=Normal  4=Aiguillage (Junction)")


class TRAINS_Props(PropertyGroup):
    filepath:   StringProperty(name="Fichier", subtype="FILE_PATH")
    track_name: StringProperty(name="Nom piste", default="trains4")
    points:     CollectionProperty(type=TRAINS_Point)
    point_idx:  IntProperty(default=-1)
    # Affichage
    show_track: BoolProperty(name="Voie",        default=True)
    show_jct:   BoolProperty(name="Aiguillages", default=True)
    # Stats
    stat_points: IntProperty(default=0)
    stat_jct:    IntProperty(default=0)


# ═══════════════════════════════════════════════════════════════════════════════
#  RACINE
# ═══════════════════════════════════════════════════════════════════════════════

class GTA5PE_Props(PropertyGroup):
    tab: EnumProperty(
        name="Module",
        items=[
            ("YNV",    "NavMesh",   "NavMesh YNV",          "MOD_FLUID",    0),
            ("YND",    "PathNodes", "PathNodes YND",         "EMPTY_ARROWS", 1),
            ("YMT",    "Scenarios", "Scenario Points YMT",   "ARMATURE_DATA",2),
            ("TRAINS", "Trains",    "Train Tracks DAT",      "CURVE_PATH",   3),
        ],
        default="YNV",
    )
    ynv:    PointerProperty(type=YNV_Props)
    ynd:    PointerProperty(type=YND_Props)
    ymt:    PointerProperty(type=YMT_Props)
    trains: PointerProperty(type=TRAINS_Props)


# ── Registration ──────────────────────────────────────────────────────────────

_CLASSES = [
    YNV_PolyFlags, YNV_Portal, YNV_NavPoint, YNV_Props,
    YND_NF0, YND_NF1, YND_NF2, YND_NF3, YND_NF4, YND_NF5,
    YND_LF0, YND_LF1, YND_LF2,
    YND_Junction, YND_JunctionRef, YND_Link, YND_Node, YND_Props,
    YMT_ScenarioPoint, YMT_ChainingNode, YMT_ChainingEdge,
    YMT_Chain, YMT_EntityOverride, YMT_Cluster, YMT_Props,
    TRAINS_Point, TRAINS_Props,
    GTA5PE_Props,
]

def register():
    for cls in _CLASSES:
        try: bpy.utils.unregister_class(cls)
        except: pass
        bpy.utils.register_class(cls)
    bpy.types.Scene.gta5pe = PointerProperty(type=GTA5PE_Props)

def unregister():
    try: del bpy.types.Scene.gta5pe
    except: pass
    for cls in reversed(_CLASSES):
        try: bpy.utils.unregister_class(cls)
        except: pass
