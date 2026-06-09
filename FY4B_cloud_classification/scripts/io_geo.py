"""GEO 几何参数读取模块"""

import os
import numpy as np
import h5py


def read_geo_angles(geo_file, geo_var_map):
    """
    读取 FY4B AGRI L1 GEO 文件中的角度信息。

    参数:
        geo_file: GEO HDF5 文件路径
        geo_var_map: 配置中的变量映射字典

    返回:
        dict: {var_name: {"data": float32 array, "attrs": dict, ...}}
    """
    out = {}
    if geo_file is None:
        print("[WARN] 没有匹配到 GEO 文件，跳过角度信息")
        return out
    if not os.path.exists(geo_file):
        print(f"[WARN] GEO 文件不存在: {geo_file}")
        return out

    with h5py.File(geo_file, "r") as h5:
        for out_name, ds_name in geo_var_map.items():
            if ds_name not in h5:
                print(f"[WARN] GEO 找不到变量 {ds_name}")
                continue

            print(f"[OK] reading GEO {out_name}: {ds_name}")
            ds = h5[ds_name]
            arr = np.array(ds[:], dtype=np.float32)
            attrs = {k: ds.attrs[k] for k in ds.attrs.keys()}

            if arr.ndim != 2:
                print(f"[WARN] GEO {out_name} 不是二维数组，shape={arr.shape}，跳过")
                continue

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
