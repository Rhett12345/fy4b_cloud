# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FY-4B AGRI satellite cloud product data pipeline. Reads Level 1B radiance and Level 2 cloud products from the FY-4B geostationary weather satellite's AGRI instrument, pairs them by time, calibrates raw counts to physical values, and outputs unified NetCDF files for a downstream cloud classification algorithm.

## Running the Main Script

```bash
cd FY4B_cloud_classification/scripts
python3 main.py \
  --root /path/to/FY4BData/YYYYMMDD/FY4B_AGRI \
  --outdir ./fy4b_cloud_inputs_nc \
  --channels C01,C02,C03,C04,C05,C06,C07,C08,C09,C10,C11,C12,C13,C14 \
  --max-time-diff-min 20
```

Dependencies: `numpy`, `h5py`, `netCDF4`, `pyyaml` (no requirements.txt — install manually).

## Data Packaging / Transfer

Shell scripts in `FY4B_cloud_classification/scripts/` package code + a subset of data (10 timestamps, 4km resolution only) into a tarball for transfer to another server. These scripts have hardcoded paths under `/home/hf/` — adjust before running on a different machine.

## Architecture

**Modular pipeline** (7 modules + YAML config):

1. **`main.py`** — Entry point, argument parsing, orchestration.
2. **`config.py`** — Loads `config/fy4b.yaml` (product dirs, variable candidates, channel definitions, GEO mapping, output settings).
3. **`matcher.py`** — Directory scanning, time index building, L1B-L2 file pairing by time proximity.
4. **`io_l1b.py`** — Reads 14 AGRI channels (C01–C14) from HDF5, applies lookup-table calibration. Outputs float32 physical values (reflectance for C01–C06, brightness temperature in K for C07–C14).
5. **`io_l2.py`** — Reads cloud mask, cloud phase, cloud type, cloud top height/temperature/pressure from NetCDF files with fuzzy variable name matching.
6. **`io_geo.py`** — Reads satellite/sun geometry angles from the GEO companion file.
7. **`writer.py`** — Writes one compressed (zlib level 4) NetCDF4 file per matched timestamp containing all products.

**Data layout convention** (raw input):
```
FY4BData/YYYYMMDD/FY4B_AGRI/
  L1_HDF/DISK/          — FDI (radiances) + GEO (geometry), HDF5, 4km
  L2_CLM_DISK/MULT/     — Cloud Mask, .NC
  L2_CLP_DISK/MULT/     — Cloud Phase, .NC
  L2_CLT_DISK/MULT/     — Cloud Type, .NC
  L2_CTH_DISK/MULT/     — Cloud Top Height, .NC
  L2_CTT_DISK/MULT/     — Cloud Top Temperature, .NC
  L2_CTP_DISK/MULT/     — Cloud Top Pressure, .NC
```

## Key Conventions

- All comments and docstrings in Python modules are in Chinese.
- FY4B product version differences are handled via candidate variable names configured in `config/fy4b.yaml`.
- Output filenames follow the pattern: `FY4B_AGRI_cloud_inputs_YYYYMMDDHHMMSS.nc`.
- L1B channels are stored as float32 physical values (no manual scaling needed downstream).
- All configuration (product dirs, variable candidates, channel definitions, output settings) lives in `config/fy4b.yaml`.
