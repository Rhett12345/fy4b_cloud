"""L2 云产品读取模块"""

import os
from io_l1b import find_dataset, read_dataset


def print_file_structure(file_path, max_items=80):
    """调试用：打印 HDF5 文件结构"""
    import h5py
    print(f"\n[结构] {file_path}")
    with h5py.File(file_path, "r") as h5:
        datasets = []
        def visitor(name, obj):
            if isinstance(obj, h5py.Dataset):
                datasets.append((name, obj))
        h5.visititems(visitor)
        for i, (name, ds) in enumerate(datasets[:max_items]):
            print(f"  {i + 1:03d} {name} shape={ds.shape} dtype={ds.dtype}")
        if len(datasets) > max_items:
            print(f"  ... 还有 {len(datasets) - max_items} 个 dataset")


def read_l2_cloud_products(product_files, l2_var_candidates):
    """
    读取所有 L2 云产品。

    参数:
        product_files: {"CLM": file_path, "CLP": file_path, ...}
        l2_var_candidates: 配置中的变量名候选字典

    返回:
        dict: {var_name: {"data": array, "attrs": dict, "dataset": str, "file": str}}
    """
    mapping = {
        "cloud_mask": "CLM",
        "cloud_phase": "CLP",
        "cloud_optical_depth": "CPD",
        "cloud_top_height": "CTH",
        "cloud_top_temperature": "CTT",
        "cloud_top_pressure": "CTP",
        "cloud_type": "CLT",
        "cloud_effective_radius": "CPD",
    }

    out = {}
    for var_name, product_key in mapping.items():
        f = product_files.get(product_key)
        if f is None:
            print(f"[WARN] 缺少 {product_key} 文件，跳过 {var_name}")
            continue

        candidates = l2_var_candidates.get(var_name, [])
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
