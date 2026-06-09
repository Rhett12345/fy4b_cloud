#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FY-4B AGRI L1B + L2 云产品数据处理主入口

功能：
1. 自动扫描 FY4B AGRI 目录
2. 按时间配对 L1B 和 L2 云产品
3. 读取云检测、云相态、云光学厚度、云顶高度、云顶温度、云顶气压等
4. 输出统一 NetCDF 文件，供后续云分类算法使用
5. 支持多进程并行处理多个时次
"""

import os
import argparse
import sys
from functools import partial
from multiprocessing import Pool

# 确保当前目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load_config, get_channel_config
from matcher import scan_all_products, match_l2_products, find_geo_file_from_l1b
from io_l1b import read_l1b_channels
from io_l2 import read_l2_cloud_products
from io_geo import read_geo_angles
from writer import write_nc
from cloud_type import run_cloud_classification


def process_one_timestamp(obs_time, indices, l2_keys, channel_configs,
                          geo_var_map, l2_var_candidates, outdir, cfg):
    """处理单个时次（可被多进程调用）"""
    import sys as _sys

    print("\n" + "-" * 80)
    print(f"[TIME] {obs_time}")

    l1b_file = indices["L1B"][obs_time]
    print(f"L1B: {l1b_file}")

    # 匹配 L2 产品
    max_minutes = cfg["time_matching"]["max_diff_minutes"]
    product_files = match_l2_products(obs_time, indices, l2_keys, max_minutes=max_minutes)

    if product_files.get("CLM") is None:
        print("[SKIP] 没有云检测 CLM，跳过该时次")
        return None

    # 匹配 GEO 文件
    geo_file = find_geo_file_from_l1b(l1b_file)
    if geo_file is None:
        print("[WARN] 没有找到对应 GEO 文件，角度信息不会写入")
    else:
        print(f"[PAIR] GEO: {geo_file}")

    # 读取数据
    l1b_data = read_l1b_channels(l1b_file, channel_configs)
    geo_data = read_geo_angles(geo_file, geo_var_map)
    l2_data = read_l2_cloud_products(product_files, l2_var_candidates)

    if not l2_data:
        print("[SKIP] 没有成功读取任何 L2 云产品")
        return None

    # 运行云分类算法
    cloud_type_result = run_cloud_classification(l1b_data, l2_data, geo_data)

    # 输出
    out_name = f"FY4B_AGRI_cloud_inputs_{obs_time.strftime('%Y%m%d%H%M%S')}.nc"
    out_nc = os.path.join(outdir, out_name)

    write_nc(
        out_nc, obs_time, l1b_data, l2_data, geo_data=geo_data,
        cloud_type_ii=cloud_type_result,
        fill_value_float=cfg["output"]["fill_value_float"],
        fill_value_int=cfg["output"]["fill_value_int"],
        complevel=cfg["output"]["complevel"],
    )

    _sys.stdout.flush()
    return out_nc


def _worker(args):
    """Pool.map 包装函数（顶层函数，可被 pickle）"""
    (obs_time, indices, l2_keys, channel_configs,
     geo_var_map, l2_var_candidates, outdir, cfg) = args
    try:
        return process_one_timestamp(
            obs_time, indices, l2_keys, channel_configs,
            geo_var_map, l2_var_candidates, outdir, cfg
        )
    except Exception as e:
        print(f"[ERROR] {obs_time}: {e}")
        import traceback
        traceback.print_exc()
        return None


def process_one_day(root, outdir, cfg, channels=None, max_time_diff_min=None, workers=1):
    """处理一天目录"""

    product_dirs = cfg["product_dirs"]
    l2_var_candidates = cfg["l2_var_candidates"]
    geo_var_map = cfg["geo_var_map"]

    if max_time_diff_min is None:
        max_time_diff_min = cfg["time_matching"]["max_diff_minutes"]

    # 确定要读取的通道
    if channels is None:
        channel_configs = cfg["channels"]
    else:
        channel_configs = []
        for ch_id in channels:
            ch_cfg = get_channel_config(cfg, ch_id)
            if ch_cfg is None:
                print(f"[WARN] 配置中没有通道 {ch_id}，跳过")
            else:
                channel_configs.append(ch_cfg)

    # 不含 L1B 的产品键
    l2_keys = [k for k in product_dirs.keys() if k != "L1B"]

    print("=" * 80)
    print(f"FY4B AGRI root: {root}")
    print(f"Output dir    : {outdir}")
    print(f"Workers       : {workers}")
    print("=" * 80)

    # 扫描所有产品目录（主进程完成，结果共享给子进程）
    indices = scan_all_products(root, product_dirs)

    if not indices.get("L1B"):
        raise FileNotFoundError("没有找到 L1B 文件，请检查 L1_HDF 目录")

    l1b_times = sorted(indices["L1B"].keys())
    print(f"\n共找到 L1B 时次: {len(l1b_times)}")

    os.makedirs(outdir, exist_ok=True)

    if workers <= 1:
        # 串行处理
        for obs_time in l1b_times:
            process_one_timestamp(
                obs_time, indices, l2_keys, channel_configs,
                geo_var_map, l2_var_candidates, outdir, cfg
            )
    else:
        # 多进程并行
        tasks = [
            (obs_time, indices, l2_keys, channel_configs,
             geo_var_map, l2_var_candidates, outdir, cfg)
            for obs_time in l1b_times
        ]
        with Pool(processes=workers) as pool:
            results = pool.map(_worker, tasks)

        success = sum(1 for r in results if r is not None)
        print(f"\n{'=' * 80}")
        print(f"处理完成: {success}/{len(l1b_times)} 个时次成功")


def main():
    parser = argparse.ArgumentParser(
        description="Read FY4B AGRI L1B and L2 cloud products, then write unified NetCDF."
    )
    parser.add_argument(
        "--root", type=str,
        default="/data/Data_yuq/FY4BData/20260513/FY4B_AGRI",
        help="FY4B AGRI daily root directory"
    )
    parser.add_argument(
        "--outdir", type=str,
        default="/data/Data_yuq/fy4b_cloud_inputs_nc",
        help="Output NetCDF directory"
    )
    parser.add_argument(
        "--channels", type=str, default=None,
        help="L1B channels to read, comma separated (default: all 14)"
    )
    parser.add_argument(
        "--max-time-diff-min", type=float, default=None,
        help="Maximum time difference for matching L2 files (default: from config)"
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to YAML config file (default: ../config/fy4b.yaml)"
    )
    parser.add_argument(
        "--workers", type=int, default=8,
        help="Number of parallel workers (default: 8, set 1 for serial)"
    )

    args = parser.parse_args()

    cfg = load_config(args.config)

    channels = None
    if args.channels:
        channels = [x.strip() for x in args.channels.split(",") if x.strip()]

    process_one_day(
        root=args.root,
        outdir=args.outdir,
        cfg=cfg,
        channels=channels,
        max_time_diff_min=args.max_time_diff_min,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
