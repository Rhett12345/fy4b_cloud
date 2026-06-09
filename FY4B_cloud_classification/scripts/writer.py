"""NetCDF 输出模块"""

import os
import numpy as np
from netCDF4 import Dataset


def write_nc(out_nc, obs_time, l1b_data, l2_data, geo_data=None,
             cloud_type_ii=None,
             fill_value_float=-9999.0, fill_value_int=-9999,
             complevel=4):
    """
    输出统一 NetCDF4 文件。

    L1B 通道直接输出物理值（float32），附带 units/long_name 属性。
    L2 产品保持原始数据类型。
    GEO 角度输出 float32。
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
            "L1B channels are stored as physical values (reflectance or brightness temperature)."
        )

        # --- L2 云产品 ---
        for var_name, item in l2_data.items():
            arr = item["data"]
            if arr.ndim != 2:
                print(f"[WARN] {var_name} 不是二维数组，shape={arr.shape}，跳过写入")
                continue

            ydim = f"{var_name}_y"
            xdim = f"{var_name}_x"
            nc.createDimension(ydim, arr.shape[0])
            nc.createDimension(xdim, arr.shape[1])

            if np.issubdtype(arr.dtype, np.integer):
                dtype = "i4"
                fv = fill_value_int
            else:
                dtype = "f4"
                fv = fill_value_float

            v = nc.createVariable(
                var_name, dtype, (ydim, xdim),
                zlib=True, complevel=complevel, fill_value=fv
            )
            data = arr.copy()
            if np.issubdtype(data.dtype, np.floating):
                data = np.where(np.isfinite(data), data, fill_value_float)
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

        # --- GEO / Navigation 角度信息 ---
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
                var_name, "f4", (ydim, xdim),
                zlib=True, complevel=complevel, fill_value=fill_value_float
            )
            data = np.where(np.isfinite(arr), arr, fill_value_float).astype(np.float32)
            v[:, :] = data

            v.source_file = item["file"]
            v.source_dataset = item["dataset"]

            if var_name in ["satellite_azimuth", "satellite_zenith",
                            "sun_azimuth", "sun_zenith", "sun_glint_angle"]:
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

        # --- L1B 通道（物理值，float32） ---
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
                var_name, "f4", (ydim, xdim),
                zlib=True, complevel=complevel, fill_value=fill_value_float
            )
            data = np.where(np.isfinite(arr), arr, fill_value_float).astype(np.float32)
            v[:, :] = data

            # 写通道属性
            attrs = item.get("attrs", {})
            v.channel = ch
            v.units = attrs.get("units", "")
            v.long_name = attrs.get("long_name", "")
            v.channel_type = attrs.get("channel_type", "")
            v.source_file = item["file"]
            v.source_dataset = item.get("dataset", "")
            if "calibration_dataset" in item:
                v.calibration_dataset = item["calibration_dataset"]

        # --- 云顶高度分类 (Cloud_Height_Class) ---
        if "cloud_mask" in l2_data and "cloud_top_height" in l2_data:
            cmm = l2_data["cloud_mask"]["data"]
            cth_arr = l2_data["cloud_top_height"]["data"].astype(np.float32)

            cloud_class = np.full(cmm.shape, 255, dtype=np.uint8)
            cloud_class[cmm == 0] = 0                                 # 晴空
            cloud_class[(cmm == 1) & (cth_arr < 3000)] = 1            # 低云
            cloud_class[(cmm == 1) & (cth_arr >= 3000) & (cth_arr < 6000)] = 2  # 中云
            cloud_class[(cmm == 1) & (cth_arr >= 6000)] = 3           # 高云

            ydim = "cloud_height_class_y"
            xdim = "cloud_height_class_x"
            nc.createDimension(ydim, cloud_class.shape[0])
            nc.createDimension(xdim, cloud_class.shape[1])

            v = nc.createVariable(
                "Cloud_Height_Class", "u1", (ydim, xdim),
                zlib=True, complevel=complevel, fill_value=255
            )
            v[:, :] = cloud_class
            v.long_name = "Cloud Height Classification"
            v.description = "Classified using Cloud Top Height"
            v.units = "category"
            v.valid_range = np.array([0, 3], dtype=np.uint8)
            v.class_0 = "Clear Sky"
            v.class_1 = "Low Cloud (CTH < 3 km)"
            v.class_2 = "Middle Cloud (3 km <= CTH < 6 km)"
            v.class_3 = "High Cloud (CTH >= 6 km)"
            v.source_cloud_mask = l2_data["cloud_mask"]["file"]
            v.source_cloud_top_height = l2_data["cloud_top_height"]["file"]

            print(f"[OK] Cloud_Height_Class: low={int(np.sum(cloud_class==1)):,}  "
                  f"mid={int(np.sum(cloud_class==2)):,}  "
                  f"high={int(np.sum(cloud_class==3)):,}  "
                  f"clear={int(np.sum(cloud_class==0)):,}")
        else:
            print("[WARN] 缺少 cloud_mask 或 cloud_top_height，跳过 Cloud_Height_Class")

        # --- 云分类结果 (算法 II) ---
        if cloud_type_ii is not None:
            arr = cloud_type_ii
            var_name = "cloud_type_ii"
            ydim = f"{var_name}_y"
            xdim = f"{var_name}_x"
            nc.createDimension(ydim, arr.shape[0])
            nc.createDimension(xdim, arr.shape[1])

            v = nc.createVariable(
                var_name, "i4", (ydim, xdim),
                zlib=True, complevel=complevel, fill_value=fill_value_int
            )
            v[:, :] = arr
            v.long_name = "Cloud Type (Algorithm II)"
            v.units = "1"
            v.valid_min = 0
            v.valid_max = 63
            v.flag_values = "0,1,2,3,4,5,6,7,8,61,62,63"
            v.flag_meanings = (
                "clear, ST_SC, AS_AC, CU, CI, NS, CB, "
                "low_ST, high_SC, CI_over_SC_ST, CI_over_AS_AC, AS_AC_over_SC_ST"
            )
            v.note = (
                "Cloud type classification based on cloud top height, temperature, "
                "phase, optical depth, and effective radius. "
                "0=clear, 1=ST/SC, 2=AS/AC, 3=CU, 4=CI, 5=NS, 6=CB, "
                "7=ST(low), 8=SC(high), 61=CI+SC/ST, 62=CI+AS/AC, 63=AS/AC+SC/ST"
            )

    print(f"\n[DONE] 输出 NC: {out_nc}")
