#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FY-4B AGRI L1B + L2 cloud products reader

第一阶段功能：
1. 自动扫描 FY4B AGRI 目录
2. 按时间配对 L1B 和 L2 云产品
3. 读取云检测、云相态、云光学厚度、云顶高度、云顶温度、云顶气压等
4. 输出统一 NetCDF 文件，供后续云分类算法使用

后续云分类需要的核心产品：
- cloud_mask       云检测
- cloud_phase      云相态
- cloud_optical_depth 云光学厚度
- cloud_top_height 云顶高度
- cloud_top_temperature 云顶温度
- cloud_top_pressure 云顶气压
- L1B channels     亮温 / 反射率辅助判断
"""

import os
import re
import glob
import argparse
from datetime import datetime
import numpy as np
import h5py
from netCDF4 import Dataset


# =========================================================
# 1. 产品目录配置
# =========================================================

PRODUCT_DIRS = {
    "L1B": "L1_HDF",
    "CLM": "L2_CLM_DISK",     # cloud mask / cloud detection
    "CLP": "L2_CLP_DISK",     # cloud phase
    "CLOD": "L2_CLOD_DISK",   # cloud optical depth
    "CTH": "L2_CTH_DISK",     # cloud top height
    "CTT": "L2_CTT_DISK",     # cloud top temperature
    "CTP": "L2_CTP_DISK",     # cloud top pressure
    "CLT": "L2_CLT_DISK",     # cloud type, optional
}


# =========================================================
# 2. 变量名候选
#    不同 FY4B 文件里的变量名可能略有差别，所以这里做宽松匹配
# =========================================================

L2_VAR_CANDIDATES = {
    "cloud_mask": [
        "CLM", "Cloud_Mask", "CloudMask", "cloud_mask", "NOMCloudMask",
        "Cloud_Detection", "CloudDetection"
    ],
    "cloud_phase": [
        "CLP", "Cloud_Phase", "CloudPhase", "cloud_phase", "NOMCloudPhase"
    ],
    "cloud_optical_depth": [
        "CLOD", "Cloud_Optical_Depth", "CloudOpticalDepth",
        "cloud_optical_depth", "Optical_Depth", "COD", "COT"
    ],
    "cloud_top_height": [
        "CTH", "Cloud_Top_Height", "CloudTopHeight",
        "cloud_top_height", "NOMCloudTopHeight"
    ],
    "cloud_top_temperature": [
        "CTT", "Cloud_Top_Temperature", "CloudTopTemperature",
        "cloud_top_temperature", "NOMCloudTopTemperature"
    ],
    "cloud_top_pressure": [
        "CTP", "Cloud_Top_Pressure", "CloudTopPressure",
        "cloud_top_pressure", "NOMCloudTopPressure"
    ],
    "cloud_type": [
        "CLT", "Cloud_Type", "CloudType", "cloud_type", "NOMCloudType"
    ],
}


# =========================================================
# FY4B AGRI L1B 通道标签
# =========================================================

L1B_NOM_LABELS_4KM = [
    "NOMChannel01",
    "NOMChannel02",
    "NOMChannel03",
    "NOMChannel04",
    "NOMChannel05",
    "NOMChannel06",
    "NOMChannel07",
    "NOMChannel08",
    "NOMChannel09",
    "NOMChannel10",
    "NOMChannel11",
    "NOMChannel12",
    "NOMChannel13",
    "NOMChannel14",
]

L1B_CAL_LABELS_4KM = [
    "CALChannel01",
    "CALChannel02",
    "CALChannel03",
    "CALChannel04",
    "CALChannel05",
    "CALChannel06",
    "CALChannel07",
    "CALChannel08",
    "CALChannel09",
    "CALChannel10",
    "CALChannel11",
    "CALChannel12",
    "CALChannel13",
    "CALChannel14",
]

CHANNEL_TO_INDEX = {
    f"C{i:02d}": i - 1 for i in range(1, 15)
}

# =========================================================
# FY4B GEO / Navigation 角度变量
# =========================================================

GEO_VAR_MAP = {
    "column_number": "Navigation/ColumnNumber",
    "line_number": "Navigation/LineNumber",
    "satellite_azimuth": "Navigation/NOMSatelliteAzimuth",
    "satellite_zenith": "Navigation/NOMSatelliteZenith",
    "sun_azimuth": "Navigation/NOMSunAzimuth",
    "sun_zenith": "Navigation/NOMSunZenith",
    "sun_glint_angle": "Navigation/NOMSunGlintAngle",
}

# =========================================================
# 3. 基础工具函数
# =========================================================

def parse_time_from_filename(path):
    """
    从 FY4B 文件名中提取时间。
    兼容：
    - 20260513000000
    - 20260513T000000
    """
    name = os.path.basename(path)

    patterns = [
        r"(20\d{12})",
        r"(20\d{6}T\d{6})",
    ]

    for p in patterns:
        m = re.search(p, name)
        if m:
            s = m.group(1)
            if "T" in s:
                return datetime.strptime(s, "%Y%m%dT%H%M%S")
            else:
                return datetime.strptime(s, "%Y%m%d%H%M%S")

    return None


def list_files(root, subdir):
    """
    扫描某个产品目录里的 HDF / H5 / NC 文件。
    L1_HDF 只保留真正观测通道文件，排除 GEO 文件。
    """
    d = os.path.join(root, subdir)

    patterns = [
        "*.HDF", "*.H5", "*.h5", "*.hdf", "*.NC", "*.nc"
    ]

    files = []
    for p in patterns:
        files.extend(glob.glob(os.path.join(d, "**", p), recursive=True))

    files = sorted(files)

    if subdir == "L1_HDF":
        files = [
            f for f in files
            if "L1-_FDI-" in os.path.basename(f)
            and "4000M" in os.path.basename(f)
        ]

    return files


def build_time_index(files):
    """
    建立 {datetime: file} 索引。
    """
    out = {}
    for f in files:
        t = parse_time_from_filename(f)
        if t is not None:
            out[t] = f
    return out


def nearest_file(target_time, time_index, max_minutes=20):
    """
    找到和目标时间最近的文件。
    """
    if not time_index:
        return None

    best_t = None
    best_dt = None

    for t in time_index.keys():
        dt = abs((t - target_time).total_seconds()) / 60.0
        if best_dt is None or dt < best_dt:
            best_dt = dt
            best_t = t

    if best_dt is not None and best_dt <= max_minutes:
        return time_index[best_t]

    return None

def find_geo_file_from_l1b(l1b_file):
    """
    根据 L1 FDI 文件路径，寻找同时间的 L1 GEO 文件。
    例如：
    L1-_FDI-_MULT_NOM_20260513020000_...
    替换为：
    L1-_GEO-_MULT_NOM_20260513020000_...
    """
    if l1b_file is None:
        return None

    geo_file = l1b_file.replace("L1-_FDI-", "L1-_GEO-")

    if os.path.exists(geo_file):
        return geo_file

    # 如果直接替换失败，就在同目录下按时间搜索
    obs_time = parse_time_from_filename(l1b_file)
    if obs_time is None:
        return None

    l1_dir = os.path.dirname(l1b_file)
    pattern = os.path.join(l1_dir, "*L1-_GEO-*4000M*.HDF")
    candidates = sorted(glob.glob(pattern))

    idx = build_time_index(candidates)
    return nearest_file(obs_time, idx, max_minutes=1)

def normalize_name(s):
    return s.lower().replace("_", "").replace("-", "").replace("/", "")


def collect_hdf5_datasets(h5):
    """
    递归收集 HDF5 文件里的所有 dataset。
    返回：
    [(dataset_path, dataset_object), ...]
    """
    datasets = []

    def visitor(name, obj):
        if isinstance(obj, h5py.Dataset):
            datasets.append((name, obj))

    h5.visititems(visitor)
    return datasets


def find_dataset(file_path, candidates):
    """
    根据候选变量名，从 HDF5 文件中找 dataset。
    """
    if file_path is None or not os.path.exists(file_path):
        return None, None

    candidates_norm = [normalize_name(c) for c in candidates]

    with h5py.File(file_path, "r") as h5:
        datasets = collect_hdf5_datasets(h5)

        # 第一轮：精确宽松匹配
        for ds_name, ds in datasets:
            n = normalize_name(ds_name)
            base = normalize_name(os.path.basename(ds_name))

            for c in candidates_norm:
                if base == c or n.endswith(c):
                    return ds_name, ds.shape

        # 第二轮：包含匹配
        for ds_name, ds in datasets:
            n = normalize_name(ds_name)
            for c in candidates_norm:
                if c in n:
                    return ds_name, ds.shape

    return None, None


def read_dataset(file_path, ds_name):
    """
    读取 dataset，并应用 scale_factor / add_offset / fill_value。
    """
    with h5py.File(file_path, "r") as h5:
        ds = h5[ds_name]
        arr = ds[...]

        attrs = {k: ds.attrs[k] for k in ds.attrs.keys()}

    arr = np.array(arr)

    fill_values = []

    for key in [
        "_FillValue", "FillValue", "fill_value",
        "missing_value", "MissingValue", "InvalidValue"
    ]:
        if key in attrs:
            v = attrs[key]
            if isinstance(v, np.ndarray):
                fill_values.extend(v.flatten().tolist())
            else:
                fill_values.append(v)

    scale = 1.0
    offset = 0.0

    for key in ["scale_factor", "ScaleFactor", "Slope", "scale"]:
        if key in attrs:
            v = attrs[key]
            scale = float(np.array(v).flatten()[0])
            break

    for key in ["add_offset", "AddOffset", "Intercept", "offset"]:
        if key in attrs:
            v = attrs[key]
            offset = float(np.array(v).flatten()[0])
            break

    # 整型质量标志类产品不要乱缩放
    if scale != 1.0 or offset != 0.0:
        arr = arr.astype(np.float32)
        for fv in fill_values:
            arr[arr == fv] = np.nan
        arr = arr * scale + offset
    else:
        if np.issubdtype(arr.dtype, np.floating):
            arr = arr.astype(np.float32)
            for fv in fill_values:
                arr[arr == fv] = np.nan

    # 如果是 3D 但第一维是 1，压成 2D
    if arr.ndim == 3 and arr.shape[0] == 1:
        arr = arr[0, :, :]

    return arr, attrs


def print_file_structure(file_path, max_items=80):
    """
    调试用：打印文件结构。
    """
    print(f"\n[结构] {file_path}")
    with h5py.File(file_path, "r") as h5:
        datasets = collect_hdf5_datasets(h5)
        for i, (name, ds) in enumerate(datasets[:max_items]):
            print(f"  {i + 1:03d} {name} shape={ds.shape} dtype={ds.dtype}")
        if len(datasets) > max_items:
            print(f"  ... 还有 {len(datasets) - max_items} 个 dataset")


# =========================================================
# 4. 读取 L1B
# =========================================================

def read_l1b_channels(l1b_file, channels):
    """
    读取 FY4B AGRI L1B 通道，并用 Calibration 查找表完成定标。

    逻辑：
    Data/NOMChannelXX 是二维码值
    Calibration/CALChannelXX 是一维查找表

    对每个像元：
    real_value = CALChannelXX[NOMChannelXX]

    缩放：
    C01-C06: 反射率，乘 10000，输出 uint16
    C07-C14: 亮温，乘 100，输出 uint16

    无效值：
    65535
    """
    out = {}

    if l1b_file is None:
        return out

    if not os.path.exists(l1b_file):
        print(f"[WARN] L1B 文件不存在: {l1b_file}")
        return out

    with h5py.File(l1b_file, "r") as h5:
        if "Data" not in h5:
            raise KeyError(f"L1B 文件中没有 Data 组: {l1b_file}")

        if "Calibration" not in h5:
            raise KeyError(f"L1B 文件中没有 Calibration 组: {l1b_file}")

        data_group = h5["Data"]
        cal_group = h5["Calibration"]

        # 自动判断行列
        sample_nom = None
        for key in L1B_NOM_LABELS_4KM:
            if key in data_group:
                sample_nom = data_group[key][:]
                break

        if sample_nom is None:
            raise KeyError(f"L1B Data 组中没有找到 NOMChannelXX: {l1b_file}")

        row, col = sample_nom.shape
        print(f"[INFO] L1B image shape: row={row}, col={col}")

        for ch in channels:
            ch = ch.strip().upper()

            if ch not in CHANNEL_TO_INDEX:
                print(f"[WARN] 未知通道 {ch}，跳过")
                continue

            idx = CHANNEL_TO_INDEX[ch]
            nom_name = L1B_NOM_LABELS_4KM[idx]
            cal_name = L1B_CAL_LABELS_4KM[idx]

            if nom_name not in data_group:
                print(f"[WARN] L1B Data 组找不到 {nom_name}，跳过 {ch}")
                continue

            if cal_name not in cal_group:
                print(f"[WARN] L1B Calibration 组找不到 {cal_name}，跳过 {ch}")
                continue

            print(f"[OK] reading L1B {ch}: Data/{nom_name} + Calibration/{cal_name}")

            nom0 = data_group[nom_name][:]
            cal0 = cal_group[cal_name][:]

            if nom0.shape != (row, col):
                print(f"[WARN] {nom_name} shape={nom0.shape} 与主尺寸 {(row, col)} 不一致，跳过")
                continue

            # C01-C06 反射率，扩大 10000
            # C07-C14 亮温，扩大 100
            if idx < 6:
                ifactor = 10000
                units = "reflectance_scaled_by_10000"
            else:
                ifactor = 100
                units = "brightness_temperature_K_scaled_by_100"

            # 按你给的逻辑：
            # NOMChannel07 特殊，最大值 65534
            # 其他通道 nom_max = 4096
            if nom_name == "NOMChannel07":
                nom_max = 65534
            else:
                nom_max = 4096

            temp = np.zeros((row, col), dtype=np.uint16) + 65535

            loc = np.where((nom0 > 0) & (nom0 < nom_max))

            # 防止个别码值超过 cal0 长度
            valid_loc = loc[0], loc[1]
            dn = nom0[valid_loc].astype(np.int64)

            inside = dn < len(cal0)
            yy = valid_loc[0][inside]
            xx = valid_loc[1][inside]
            dn = dn[inside]

            values = cal0[dn] * ifactor

            # 防止溢出
            values = np.where(np.isfinite(values), values, 65535)
            values = np.clip(values, 0, 65534)

            temp[yy, xx] = values.astype(np.uint16)

            out[ch] = {
                "data": temp,
                "attrs": {
                    "channel": ch,
                    "nom_dataset": f"Data/{nom_name}",
                    "cal_dataset": f"Calibration/{cal_name}",
                    "scale_factor_for_storage": ifactor,
                    "units": units,
                    "valid_min": 0,
                    "valid_max": 65534,
                    "fill_value": 65535,
                },
                "dataset": f"Data/{nom_name}",
                "calibration_dataset": f"Calibration/{cal_name}",
                "file": l1b_file,
            }

            print(f"[OK] L1B {ch}: calibrated shape={temp.shape}, dtype={temp.dtype}")

    return out

# =========================================================
# 4.1 读取 GEO 角度信息
# =========================================================

def read_geo_angles(geo_file):
    """
    读取 FY4B AGRI L1 GEO 文件中的角度信息。

    主要变量：
    - satellite_azimuth
    - satellite_zenith
    - sun_azimuth
    - sun_zenith
    - sun_glint_angle
    - line_number
    - column_number

    说明：
    角度变量中 65535 通常表示无效值。
    ColumnNumber / LineNumber 里 -1 通常表示无效值。
    """
    out = {}

    if geo_file is None:
        print("[WARN] 没有匹配到 GEO 文件，跳过角度信息")
        return out

    if not os.path.exists(geo_file):
        print(f"[WARN] GEO 文件不存在: {geo_file}")
        return out

    with h5py.File(geo_file, "r") as h5:
        for out_name, ds_name in GEO_VAR_MAP.items():
            if ds_name not in h5:
                print(f"[WARN] GEO 找不到变量 {ds_name}")
                continue

            print(f"[OK] reading GEO {out_name}: {ds_name}")

            ds = h5[ds_name]
            arr = ds[:]
            attrs = {k: ds.attrs[k] for k in ds.attrs.keys()}

            arr = np.array(arr)

            if arr.ndim != 2:
                print(f"[WARN] GEO {out_name} 不是二维数组，shape={arr.shape}，跳过")
                continue

            # 统一转成 float32，方便后面处理角度缺测
            arr = arr.astype(np.float32)

            # 角度变量：65535 是无效值
            if out_name not in ["line_number", "column_number"]:
                arr[arr >= 65535] = np.nan

            # 行列号：-1 是无效值
            if out_name in ["line_number", "column_number"]:
                arr[arr < 0] = np.nan

            out[out_name] = {
                "data": arr,
                "attrs": attrs,
                "dataset": ds_name,
                "file": geo_file,
            }

            print(f"[OK] GEO {out_name}: shape={arr.shape}, dtype={arr.dtype}")

    return out

# =========================================================
# 5. 读取 L2 云产品
# =========================================================

def read_l2_cloud_products(product_files):
    """
    读取所有 L2 云产品。
    product_files:
    {
        "CLM": file,
        "CLP": file,
        ...
    }
    """
    mapping = {
        "cloud_mask": "CLM",
        "cloud_phase": "CLP",
        "cloud_optical_depth": "CLOD",
        "cloud_top_height": "CTH",
        "cloud_top_temperature": "CTT",
        "cloud_top_pressure": "CTP",
        "cloud_type": "CLT",
    }

    out = {}

    for var_name, product_key in mapping.items():
        f = product_files.get(product_key)

        if f is None:
            print(f"[WARN] 缺少 {product_key} 文件，跳过 {var_name}")
            continue

        candidates = L2_VAR_CANDIDATES[var_name]
        ds_name, shape = find_dataset(f, candidates)

        if ds_name is None:
            print(f"[WARN] {product_key} 找不到变量 {var_name}: {f}")
            print_file_structure(f, max_items=40)
            continue

        arr, attrs = read_dataset(f, ds_name)

        out[var_name] = {
            "data": arr,
            "attrs": attrs,
            "dataset": ds_name,
            "file": f,
        }

        print(f"[OK] {product_key} -> {var_name}: {ds_name}, shape={arr.shape}")

    return out


# =========================================================
# 6. NetCDF 输出
# =========================================================

def nc_dtype(arr):
    if np.issubdtype(arr.dtype, np.integer):
        return "i4"
    else:
        return "f4"


def write_nc(out_nc, obs_time, l1b_data, l2_data, geo_data=None):
    """
    输出统一 NC。
    注意：
    - 不强制重采样
    - 每个变量保留自己的 y/x 维度
    - 后续云分类时，需要统一到目标分辨率
    """
    if geo_data is None:
        geo_data = {}

    os.makedirs(os.path.dirname(out_nc), exist_ok=True)

    with Dataset(out_nc, "w", format="NETCDF4") as nc:
        nc.title = "FY4B AGRI L1B and L2 cloud products"
        nc.satellite = "FY-4B"
        nc.sensor = "AGRI"
        nc.time = obs_time.strftime("%Y-%m-%d %H:%M:%S")
        nc.note = (
            "This file contains matched FY4B AGRI L1B and L2 cloud products. "
            "No resampling is applied in this reader."
        )

        # -----------------------------
        # 写 L2 云产品
        # -----------------------------
        for var_name, item in l2_data.items():
            arr = item["data"]

            if arr.ndim != 2:
                print(f"[WARN] {var_name} 不是二维数组，shape={arr.shape}，跳过写入")
                continue

            ydim = f"{var_name}_y"
            xdim = f"{var_name}_x"

            nc.createDimension(ydim, arr.shape[0])
            nc.createDimension(xdim, arr.shape[1])

            v = nc.createVariable(
                var_name,
                nc_dtype(arr),
                (ydim, xdim),
                zlib=True,
                complevel=4,
                fill_value=-9999.0 if not np.issubdtype(arr.dtype, np.integer) else -9999
            )

            data = arr.copy()
            if np.issubdtype(data.dtype, np.floating):
                data = np.where(np.isfinite(data), data, -9999.0)

            v[:, :] = data

            v.source_file = item["file"]
            v.source_dataset = item["dataset"]

            for k, val in item["attrs"].items():
                try:
                    if isinstance(val, bytes):
                        val = val.decode("utf-8", errors="ignore")
                    elif isinstance(val, np.ndarray):
                        if val.size <= 8:
                            val = val.tolist()
                        else:
                            continue
                    setattr(v, str(k), val)
                except Exception:
                    pass


        # -----------------------------
        # 写 GEO / Navigation 角度信息
        # -----------------------------
        for var_name, item in geo_data.items():
            arr = item["data"]

            if arr.ndim != 2:
                print(f"[WARN] GEO {var_name} 不是二维数组，shape={arr.shape}，跳过写入")
                continue

            ydim = f"{var_name}_y"
            xdim = f"{var_name}_x"

            nc.createDimension(ydim, arr.shape[0])
            nc.createDimension(xdim, arr.shape[1])

            v = nc.createVariable(
                var_name,
                "f4",
                (ydim, xdim),
                zlib=True,
                complevel=4,
                fill_value=-9999.0
            )

            data = arr.astype(np.float32)
            data = np.where(np.isfinite(data), data, -9999.0)

            v[:, :] = data

            v.source_file = item["file"]
            v.source_dataset = item["dataset"]

            if var_name in [
                "satellite_azimuth",
                "satellite_zenith",
                "sun_azimuth",
                "sun_zenith",
                "sun_glint_angle",
            ]:
                v.units = "degree"
                v.valid_min = 0.0
                v.valid_max = 360.0

            if var_name in ["line_number", "column_number"]:
                v.units = "pixel_index"

            for k, val in item.get("attrs", {}).items():
                try:
                    if isinstance(val, bytes):
                        val = val.decode("utf-8", errors="ignore")
                    elif isinstance(val, np.ndarray):
                        if val.size <= 8:
                            val = val.tolist()
                        else:
                            continue
                    setattr(v, str(k), val)
                except Exception:
                    pass

        # -----------------------------
        # 写 L1B 通道
        # -----------------------------
        for ch, item in l1b_data.items():
            arr = item["data"]

            if arr.ndim != 2:
                print(f"[WARN] L1B {ch} 不是二维数组，shape={arr.shape}，跳过写入")
                continue

            var_name = f"l1b_{ch}"

            ydim = f"{var_name}_y"
            xdim = f"{var_name}_x"

            nc.createDimension(ydim, arr.shape[0])
            nc.createDimension(xdim, arr.shape[1])

            v = nc.createVariable(
                var_name,
                "u2",
                (ydim, xdim),
                zlib=True,
                complevel=4,
                fill_value=np.uint16(65535)
            )

            v[:, :] = arr.astype(np.uint16)

            v.source_file = item["file"]
            v.source_dataset = item["dataset"]
            v.channel = ch

            if "calibration_dataset" in item:
                v.calibration_dataset = item["calibration_dataset"]

            # 写自定义属性
            for k, val in item.get("attrs", {}).items():
                try:
                    setattr(v, str(k), val)
                except Exception:
                    pass


    print(f"\n[DONE] 输出 NC: {out_nc}")


# =========================================================
# 7. 主流程
# =========================================================

def process_one_day(root, outdir, channels, max_time_diff_min=20):
    """
    处理一天目录，例如：
    /home/hf/FY4BData/20260513/FY4B_AGRI
    """

    print("=" * 80)
    print(f"FY4B AGRI root: {root}")
    print(f"Output dir    : {outdir}")
    print("=" * 80)

    # -----------------------------
    # 建立所有产品时间索引
    # -----------------------------
    indices = {}

    for key, subdir in PRODUCT_DIRS.items():
        files = list_files(root, subdir)
        idx = build_time_index(files)
        indices[key] = idx

        print(f"[SCAN] {key:5s} {subdir:15s}: files={len(files)}, valid_time={len(idx)}")

    if not indices["L1B"]:
        raise FileNotFoundError("没有找到 L1B 文件，请检查 L1_HDF 目录")

    # 用 L1B 时间作为主时间轴
    l1b_times = sorted(indices["L1B"].keys())

    print(f"\n共找到 L1B 时次: {len(l1b_times)}")

    for obs_time in l1b_times:
        print("\n" + "-" * 80)
        print(f"[TIME] {obs_time}")

        l1b_file = indices["L1B"][obs_time]
        print(f"L1B: {l1b_file}")

        product_files = {}

        for key in PRODUCT_DIRS.keys():
            if key == "L1B":
                continue

            f = nearest_file(
                obs_time,
                indices.get(key, {}),
                max_minutes=max_time_diff_min
            )

            product_files[key] = f

            if f is None:
                print(f"[MISS] {key}: no matched file")
            else:
                print(f"[PAIR] {key}: {f}")

        # 至少有 CLM 才继续
        if product_files.get("CLM") is None:
            print("[SKIP] 没有云检测 CLM，跳过该时次")
            continue

        geo_file = find_geo_file_from_l1b(l1b_file)

        if geo_file is None:
            print("[WARN] 没有找到对应 GEO 文件，角度信息不会写入")
        else:
            print(f"[PAIR] GEO: {geo_file}")

        l1b_data = read_l1b_channels(l1b_file, channels)
        geo_data = read_geo_angles(geo_file)
        l2_data = read_l2_cloud_products(product_files)

        if not l2_data:
            print("[SKIP] 没有成功读取任何 L2 云产品")
            continue

        out_name = f"FY4B_AGRI_cloud_inputs_{obs_time.strftime('%Y%m%d%H%M%S')}.nc"
        out_nc = os.path.join(outdir, out_name)

        write_nc(out_nc, obs_time, l1b_data, l2_data, geo_data=geo_data)


def main():
    parser = argparse.ArgumentParser(
        description="Read FY4B AGRI L1B and L2 cloud products, then write unified NetCDF."
    )

    parser.add_argument(
        "--root",
        type=str,
        default="/data/Data_yuq/FY4BData/20260513/FY4B_AGRI",
        help="FY4B AGRI daily root directory"
    )

    parser.add_argument(
        "--outdir",
        type=str,
        default="/data/Data_yuq/fy4b_cloud_inputs_nc",
        help="Output NetCDF directory"
    )

    parser.add_argument(
        "--channels",
        type=str,
        default="C01,C02,C03,C04,C05,C06,C07,C08,C09,C10,C11,C12,C13,C14",
        help="L1B channels to read, comma separated"
    )

    parser.add_argument(
        "--max-time-diff-min",
        type=float,
        default=20,
        help="Maximum time difference for matching L2 files"
    )

    args = parser.parse_args()

    channels = [x.strip() for x in args.channels.split(",") if x.strip()]

    process_one_day(
        root=args.root,
        outdir=args.outdir,
        channels=channels,
        max_time_diff_min=args.max_time_diff_min
    )


if __name__ == "__main__":
    main()