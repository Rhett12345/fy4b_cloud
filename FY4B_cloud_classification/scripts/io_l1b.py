"""L1B 通道读取与标定模块"""

import os
import numpy as np
import h5py


def _collect_hdf5_datasets(h5):
    """递归收集 HDF5 文件里的所有 dataset"""
    datasets = []
    def visitor(name, obj):
        if isinstance(obj, h5py.Dataset):
            datasets.append((name, obj))
    h5.visititems(visitor)
    return datasets


def _normalize_name(s):
    return s.lower().replace("_", "").replace("-", "").replace("/", "")


def find_dataset(file_path, candidates):
    """根据候选变量名，从 HDF5 文件中找 dataset"""
    if file_path is None or not os.path.exists(file_path):
        return None, None
    candidates_norm = [_normalize_name(c) for c in candidates]
    with h5py.File(file_path, "r") as h5:
        datasets = _collect_hdf5_datasets(h5)
        for ds_name, ds in datasets:
            n = _normalize_name(ds_name)
            base = _normalize_name(os.path.basename(ds_name))
            for c in candidates_norm:
                if base == c or n.endswith(c):
                    return ds_name, ds.shape
        for ds_name, ds in datasets:
            n = _normalize_name(ds_name)
            for c in candidates_norm:
                if c in n:
                    return ds_name, ds.shape
    return None, None


def read_dataset(file_path, ds_name):
    """读取 dataset，并应用 scale_factor / add_offset / fill_value"""
    with h5py.File(file_path, "r") as h5:
        ds = h5[ds_name]
        arr = ds[...]
        attrs = {k: ds.attrs[k] for k in ds.attrs.keys()}
    arr = np.array(arr)

    fill_values = []
    for key in ["_FillValue", "FillValue", "fill_value",
                 "missing_value", "MissingValue", "InvalidValue"]:
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

    if arr.ndim == 3 and arr.shape[0] == 1:
        arr = arr[0, :, :]

    return arr, attrs


def read_l1b_channels(l1b_file, channel_configs):
    """
    读取 FY4B AGRI L1B 通道并完成标定。

    返回 dict: {channel_id: {"data": float32 array, "attrs": dict, ...}}
    data 直接为物理值（反射率或亮温），无额外缩放。
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
        for ch_cfg in channel_configs:
            if ch_cfg["nom"] in data_group:
                sample_nom = data_group[ch_cfg["nom"]][:]
                break
        if sample_nom is None:
            raise KeyError(f"L1B Data 组中没有找到 NOMChannelXX: {l1b_file}")

        row, col = sample_nom.shape
        print(f"[INFO] L1B image shape: row={row}, col={col}")

        for ch_cfg in channel_configs:
            ch_id = ch_cfg["id"]
            nom_name = ch_cfg["nom"]
            cal_name = ch_cfg["cal"]
            nom_max = ch_cfg["nom_max"]

            if nom_name not in data_group:
                print(f"[WARN] L1B Data 组找不到 {nom_name}，跳过 {ch_id}")
                continue
            if cal_name not in cal_group:
                print(f"[WARN] L1B Calibration 组找不到 {cal_name}，跳过 {ch_id}")
                continue

            print(f"[OK] reading L1B {ch_id}: Data/{nom_name} + Calibration/{cal_name}")

            nom0 = data_group[nom_name][:]
            cal0 = cal_group[cal_name][:]

            if nom0.shape != (row, col):
                print(f"[WARN] {nom_name} shape={nom0.shape} 与主尺寸不一致，跳过")
                continue

            # 标定：直接输出物理值（float32）
            physical = np.full((row, col), np.nan, dtype=np.float32)
            loc = np.where((nom0 > 0) & (nom0 < nom_max))
            valid_loc = loc[0], loc[1]
            dn = nom0[valid_loc].astype(np.int64)

            inside = dn < len(cal0)
            yy = valid_loc[0][inside]
            xx = valid_loc[1][inside]
            dn = dn[inside]

            physical[yy, xx] = cal0[dn].astype(np.float32)

            out[ch_id] = {
                "data": physical,
                "attrs": {
                    "channel": ch_id,
                    "units": ch_cfg["units"],
                    "long_name": ch_cfg["long_name"],
                    "channel_type": ch_cfg["type"],
                    "nom_dataset": f"Data/{nom_name}",
                    "cal_dataset": f"Calibration/{cal_name}",
                    "_FillValue": np.float32(np.nan),
                },
                "dataset": f"Data/{nom_name}",
                "calibration_dataset": f"Calibration/{cal_name}",
                "file": l1b_file,
            }

            print(f"[OK] L1B {ch_id}: calibrated shape={physical.shape}, "
                  f"dtype={physical.dtype}, type={ch_cfg['type']}")

    return out
