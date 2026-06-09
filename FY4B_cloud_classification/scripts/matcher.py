"""时间匹配模块：扫描目录、建立时间索引、按时间配对文件"""

import os
import re
import glob
from datetime import datetime


def parse_time_from_filename(path):
    """从 FY4B 文件名中提取时间"""
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
    """扫描某个产品目录里的 HDF / H5 / NC 文件"""
    d = os.path.join(root, subdir)
    patterns = ["*.HDF", "*.H5", "*.h5", "*.hdf", "*.NC", "*.nc"]
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
    """建立 {datetime: file} 索引"""
    out = {}
    for f in files:
        t = parse_time_from_filename(f)
        if t is not None:
            out[t] = f
    return out


def nearest_file(target_time, time_index, max_minutes=20):
    """找到和目标时间最近的文件"""
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
    """根据 L1 FDI 文件路径，寻找同时间的 L1 GEO 文件"""
    if l1b_file is None:
        return None
    geo_file = l1b_file.replace("L1-_FDI-", "L1-_GEO-")
    if os.path.exists(geo_file):
        return geo_file
    obs_time = parse_time_from_filename(l1b_file)
    if obs_time is None:
        return None
    l1_dir = os.path.dirname(l1b_file)
    pattern = os.path.join(l1_dir, "*L1-_GEO-*4000M*.HDF")
    candidates = sorted(glob.glob(pattern))
    idx = build_time_index(candidates)
    return nearest_file(obs_time, idx, max_minutes=1)


def scan_all_products(root, product_dirs):
    """扫描所有产品目录，返回时间索引字典"""
    indices = {}
    for key, subdir in product_dirs.items():
        files = list_files(root, subdir)
        idx = build_time_index(files)
        indices[key] = idx
        print(f"[SCAN] {key:5s} {subdir:15s}: files={len(files)}, valid_time={len(idx)}")
    return indices


def match_l2_products(obs_time, indices, product_keys, max_minutes=20):
    """为一个L1B时次匹配所有L2产品文件"""
    product_files = {}
    for key in product_keys:
        f = nearest_file(obs_time, indices.get(key, {}), max_minutes=max_minutes)
        product_files[key] = f
        if f is None:
            print(f"[MISS] {key}: no matched file")
        else:
            print(f"[PAIR] {key}: {f}")
    return product_files
