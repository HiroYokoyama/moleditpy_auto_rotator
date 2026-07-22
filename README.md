# Auto Rotator Plugin

[![CI](https://github.com/HiroYokoyama/moleditpy_auto_rotator/actions/workflows/ci.yml/badge.svg)](https://github.com/HiroYokoyama/moleditpy_auto_rotator/actions/workflows/ci.yml)
![Test Coverage](https://img.shields.io/badge/coverage->80%25-green)
[![Downloads](https://img.shields.io/github/downloads/HiroYokoyama/moleditpy_auto_rotator/total)](https://github.com/HiroYokoyama/moleditpy_auto_rotator/releases)

## Overview
Auto Rotator is a small view plugin for MoleditPy that continuously spins the 3D
viewer. Like the companion [Rotation Giffer](https://github.com/HiroYokoyama/moleditpy_rotation_giffer),
it orbits the *camera* rather than moving the molecule, keeping lighting and
geometry fixed while the view rotates. Unlike the Giffer it produces no file —
it just animates the live window so you can present or inspect a structure hands-free.

## Key Features
* **Live rotation:** Starts an on-screen spin driven by a lightweight timer.
* **Six axes:** Orbit around the absolute Global axes (X, Y, Z) or the relative
  view axes — Roll (line of sight), Elevation (pitch), and Azimuth (yaw).
* **Speed control:** Set the angular speed in degrees per second; negative values
  reverse the direction.
* **Start/Stop:** Toggle the motion at any time; closing the dialog stops it cleanly.

## Requirements
This plugin relies on the host application's environment (a PyVista `plotter` and
PyQt6 UI):
* `PyQt6`
* `numpy`
* `pyvista`

## Usage Instructions
1. Load a molecule (or any 3D object) in the main viewer.
2. Open the **View** menu and select **Auto Rotator...**.
3. Choose a **Rotation Axis** and set the **Speed** (°/s; negative reverses).
4. Click **Start** to spin the view and **Stop** to halt. Closing the dialog
   stops the rotation.

## Development and Testing

This repository includes a headless unit-test suite covering dialog setup,
the start/stop timer logic, the per-tick speed scaling, and the camera
rotation mathematics.

```bash
python -m pytest tests/ -v
```
