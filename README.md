# GTA V Patchs Editor Tools – Blender Addon

## Overview

This Blender addon provides a complete workflow for importing, editing, and creating core GTA V navigation and scenario-related files directly inside Blender. It is designed for modders, map creators, and FiveM developers who want full control over AI navigation, traffic paths, scenarios, and train systems.

## Supported File Types

The addon supports the following GTA V file formats:

* `.ynd` – Vehicle navigation nodes (traffic paths)
* `.ynv` – Navmesh (pedestrian navigation)
* `scenario.ymt` – Scenario definitions (ambient events, NPC behaviors)
* `trains.dat` – Train track and path configurations

## Features

### Import

* Load existing `.ynd`, `.ynv`, `scenario.ymt`, and `trains.dat` files into Blender
* Automatic parsing and reconstruction of data into editable Blender objects
* Visual representation of:

  * Road nodes and links
  * Navmesh polygons and boundaries
  * Scenario points and regions
  * Train paths and splines

### Editing

* Modify navigation nodes, links, and flags
* Edit navmesh geometry with full vertex/face control
* Adjust scenario placements, types, and parameters
* Update train tracks, directions, and connections
* Real-time visual feedback for all changes

### Creation

* Create `.ynd` networks from scratch (roads, intersections, AI paths)
* Generate `.ynv` navmeshes for pedestrian navigation
* Build custom scenario setups (ambient life, events, zones)
* Design train routes and export to `trains.dat`
* Tools optimized for GTA V and FiveM pipelines

### Export

* Export edited or newly created data back into:

  * `.ynd`
  * `.ynv`
  * `scenario.ymt`
  * `trains.dat`
* Compatible with CodeWalker and in-game usage
* Maintains correct structure and formatting for GTA V engine

## Workflow

1. Import existing GTA V file or start from scratch
2. Edit or create elements using Blender tools
3. Validate structure using built-in checks (if enabled)
4. Export the file
5. Test in-game or in CodeWalker

## Use Cases

* Custom map creation (FiveM / Singleplayer)
* AI traffic path redesign
* Pedestrian navigation optimization
* Scenario and ambient life customization
* Train system modifications
* Full environment simulation control

## Requirements

* Blender 4.x
* Basic knowledge of GTA V modding pipeline
* Recommended tools:

  * CodeWalker
  * Sollumz

## Notes

* This addon aims to replicate and extend the functionality of existing GTA V tools directly inside Blender
* Designed for performance and accuracy with large-scale maps
* Supports iterative workflows for professional-grade projects

## Future Improvements

* Advanced validation tools
* AI-assisted path generation
* Improved visualization shaders (CodeWalker-like rendering)
* Full pipeline automation for FiveM deployment

## Disclaimer

This tool is intended for modding purposes only. GTA V assets and formats belong to Rockstar Games.

---

**Author:** [XLFrame / XLTeam]
**Version:** 1.0
**Target:** GTA V / FiveM Modding
