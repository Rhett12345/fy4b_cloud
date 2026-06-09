"""云分类算法模块（numpy 向量化版本）

基于 AGRI_cloud_type_II.f90 移植，实现 FY-4B AGRI 云分类。

云类型编码:
    0  = 无云/缺失
    1  = ST/SC (层云/层积云)
    2  = AS/AC (高层云/高积云)
    3  = CU (积云)
    4  = CI (卷云)
    5  = NS (雨层云)
    6  = CB (积雨云)
    7  = ST (低层云, 高度≤1.1km)
    8  = SC (层积云, 高度>1.1km)
    61 = CI+SC/ST (卷云覆盖层云, 多层云)
    62 = CI+AS/AC (卷云覆盖高积云, 多层云)
    63 = AS/AC+SC/ST (高积云覆盖层云, 多层云)
"""

import numpy as np


# 算法常量
ZEN_MAX = 70.0        # 卫星天顶角上限
SOLZEN_MAX = 65.0     # 太阳天顶角上限
BT14_MIN = 160.0      # 通道14亮温下限
BT14_MAX = 380.0      # 通道14亮温上限

# 4类云的标准微物理参数 (ST/SC, AS/AC, CU/CB, CI)
R_STANDARD = np.array([13.5, 17.0, 27.5, 55.0])    # 有效半径 (um)
OT_STANDARD = np.array([5.5, 17.0, 26.5, 3.5])      # 光学厚度
H_STANDARD = np.array([1.3, 3.5, 3.3, 9.5])          # 云顶高度 (km)

# 青藏高原云顶高度阈值 (海拔≥3000m时使用)
H_TIBET = np.array([1.0, 3.0, 3.3, 8.0])


def _agri_change_vec(cloudtop_hei):
    """位势高度转几何高度（numpy 向量化）

    Args:
        cloudtop_hei: 云顶位势高度 (m), 任意形状数组

    Returns:
        几何高度 (m), 同形状数组
    """
    r = 6370856.0
    dh = cloudtop_hei / 10.0
    # i: (11,1,1), dh: (1,...)  → hi: (11,...)
    i = np.arange(11, dtype=np.float32).reshape(-1, *([1] * cloudtop_hei.ndim))
    dh = dh[None, ...]
    hi = i * dh + r
    gi = 9.8 * (r / hi) ** 2
    gm = np.mean(gi, axis=0)
    return cloudtop_hei * 9.8 / gm


def _classify_vec(height, phase, radius, opti, elevation, temp, tbb):
    """向量化云分类主逻辑

    所有输入均为同尺寸二维数组 (ny, nx)。
    返回云类型数组 (int32)，无效像素填 0。
    """
    # --- 选择高度阈值 (Tibet vs Standard) ---
    is_tibet = elevation >= 3000.0
    # hh: (ny, nx, 4)
    hh = np.where(is_tibet[..., None], H_TIBET, H_STANDARD)

    # --- 基础条件掩码 ---
    is_multilayer = (height > 6.5) & (opti > 8.0)
    is_thick = opti >= 50.0
    is_normal = ~is_multilayer & ~is_thick

    # --- 多层云分类 ---
    ml_type = np.full(height.shape, 0, dtype=np.int32)
    dt = tbb - temp
    ml_type = np.where(opti < 19.0, 61, ml_type)
    ml_type = np.where((opti >= 19.0) & (dt > 20.0), 61, ml_type)
    ml_type = np.where((opti >= 19.0) & (dt <= 20.0) & (opti < 40.0), 62, ml_type)
    ml_type = np.where((opti >= 40.0) & (height < 11.0), 5, ml_type)
    ml_type = np.where((opti >= 40.0) & (height >= 11.0), 6, ml_type)

    # --- 厚云分类 ---
    tk_type = np.full(height.shape, 63, dtype=np.int32)
    tk_type = np.where((height > 4.0) & (radius < 30.0), 5, tk_type)
    tk_type = np.where((height > 4.0) & (radius >= 30.0), 6, tk_type)

    # --- 模糊匹配分类 ---
    # dh, dr, dot: (ny, nx, 4)
    dh = height[..., None] - hh
    dr = radius[..., None] - R_STANDARD
    dot = opti[..., None] - OT_STANDARD

    pdh = 0.5 * np.abs(dh) / np.maximum(height[..., None], 1e-6)
    pdr = 0.25 * np.abs(dr) / np.maximum(radius[..., None], 1e-6)
    pdot = 0.25 * np.abs(dot) / np.maximum(opti[..., None], 1e-6)

    countt = pdh + pdr + pdot
    ik = np.argmin(countt, axis=-1) + 1  # 1-based
    fz_type = ik.astype(np.int32)

    # --- 合并三种分类 ---
    typee = np.where(is_multilayer, ml_type, np.where(is_thick, tk_type, fz_type))

    # --- 修正链 ---
    typee = _refine_round1_vec(typee, height, opti)
    typee = _refine_round2_vec(typee, height, opti)
    typee = _refine_round3_vec(typee, opti, height)
    typee = _refine_final_vec(typee, height, radius, phase, opti, tbb, temp)

    return typee


def _refine_round1_vec(typee, height, opti):
    """第一轮修正（向量化）"""
    t = typee.copy()
    t = np.where((typee == 1) & (height > 3.5) & (height < 6.0), 2, t)
    t = np.where((typee == 1) & (height >= 6.0), 4, t)
    t = np.where((typee == 2) & (height > 6.0) & (opti > 32.0), 6, t)
    t = np.where((typee == 2) & (height < 3.5) & (opti < 10.0), 1, t)
    t = np.where((typee == 2) & (height < 2.5), 1, t)
    t = np.where((typee == 4) & (height < 6.0), 2, t)
    return t


def _refine_round2_vec(typee, height, opti):
    """第二轮修正（向量化）"""
    t = typee.copy()
    t = np.where((typee == 2) & (height > 6.0) & (opti <= 8.0), 4, t)
    t = np.where((typee == 2) & (opti < 2.0) & (height > 5.5), 4, t)
    t = np.where((typee == 63) & (height < 3.0), 1, t)
    return t


def _refine_round3_vec(typee, opti, height):
    """第三轮修正（向量化）"""
    t = typee.copy()
    t = np.where(typee == 61, 62, t)
    t = np.where((typee == 62) & (opti > 24), 5, t)
    t = np.where((typee == 1) & (height <= 1.1), 7, t)
    t = np.where((typee == 1) & (height > 1.1), 8, t)
    t = np.where((typee == 6) & (height < 4.5), 3, t)
    return t


def _refine_final_vec(typee, height, radius, phase, opti, tbb, temp):
    """最终修正（向量化）"""
    t = typee.copy()
    dt = tbb - temp

    t = np.where((typee == 6) & (radius < 10.0), 5, t)
    t = np.where((typee == 2) & (height <= 3.0) & (dt < 2.0), 8, t)
    t = np.where((typee == 2) & (opti > 32.0), 63, t)
    t = np.where((typee == 5) & (height >= 11.0), 6, t)
    t = np.where((typee == 6) & (dt > 15.0), 62, t)
    t = np.where((typee == 2) & (radius > 30.0), 3, t)
    t = np.where((typee == 8) & (radius > 25.0) & (phase == 1), 3, t)
    t = np.where((typee == 7) & (radius > 25.0) & (phase == 1), 3, t)
    t = np.where((typee == 3) & (opti > 35.0), 6, t)
    t = np.where((typee == 5) & (dt <= 0.0), 6, t)
    t = np.where((typee == 5) & (dt > 20.0), 61, t)
    t = np.where((typee == 62) & (dt > 20.0), 61, t)
    t = np.where((typee == 8) & (opti > 32.0), 3, t)
    t = np.where((typee == 7) & (opti > 32.0), 3, t)
    t = np.where((typee == 5) & (dt <= 0), 6, t)
    t = np.where((typee == 8) & (dt <= -2), 3, t)
    t = np.where((typee == 7) & (dt <= -2), 3, t)
    t = np.where((typee == 2) & (height > 6.0) & (opti > 24.0), 6, t)
    t = np.where((typee == 61) & (opti > 24.0), 6, t)
    t = np.where((typee == 62) & (opti > 24), 5, t)
    t = np.where((typee == 6) & (radius < 25.0) & (height < 11.0), 5, t)
    t = np.where((typee == 63) & (opti > 42.0), 5, t)
    t = np.where((typee == 3) & (opti > 30.0), 5, t)
    t = np.where((typee == 8) & (opti >= 16.0), 5, t)
    t = np.where((typee == 7) & (opti >= 16.0), 5, t)
    return t


def run_cloud_classification(l1b_data, l2_data, geo_data, zsfc=None):
    """运行云分类算法（numpy 向量化）

    Args:
        l1b_data: L1B数据字典 (需要 C14)
        l2_data: L2数据字典 (需要 cloud_phase, cloud_top_height,
                 cloud_top_temperature; 可选 cloud_optical_depth, cloud_effective_radius)
        geo_data: GEO角度数据字典 (需要 sun_zenith, satellite_zenith)
        zsfc: 地表高度数组 (m), None则使用0

    Returns:
        np.ndarray: 云类型数组 (int32), 与输入同尺寸
        或 None: 如果缺少必要输入
    """
    # 检查必要输入
    required_l1b = ["C14"]
    required_l2 = ["cloud_phase", "cloud_top_height", "cloud_top_temperature"]
    required_geo = ["sun_zenith", "satellite_zenith"]

    for k in required_l1b:
        if k not in l1b_data:
            print(f"[WARN] 云分类缺少 L1B 输入: {k}，跳过云分类")
            return None
    for k in required_l2:
        if k not in l2_data:
            print(f"[WARN] 云分类缺少 L2 输入: {k}，跳过云分类")
            return None
    for k in required_geo:
        if k not in geo_data:
            print(f"[WARN] 云分类缺少 GEO 输入: {k}，跳过云分类")
            return None

    bt14 = l1b_data["C14"]["data"].astype(np.float32)
    phase = l2_data["cloud_phase"]["data"]
    cth = l2_data["cloud_top_height"]["data"].astype(np.float32)
    ctt = l2_data["cloud_top_temperature"]["data"].astype(np.float32)
    sunzen = geo_data["sun_zenith"]["data"].astype(np.float32)
    vzen = geo_data["satellite_zenith"]["data"].astype(np.float32)

    # 可选输入
    has_cod = "cloud_optical_depth" in l2_data
    has_cer = "cloud_effective_radius" in l2_data

    if has_cod:
        cod = l2_data["cloud_optical_depth"]["data"].astype(np.float32)
    else:
        print("[WARN] 缺少云光学厚度 (cloud_optical_depth)，云分类将标记为缺失")
        cod = None

    if has_cer:
        cer = l2_data["cloud_effective_radius"]["data"].astype(np.float32)
    else:
        print("[WARN] 缺少云有效粒子半径 (cloud_effective_radius)，云分类将标记为缺失")
        cer = None

    ny, nx = bt14.shape
    fill_int = -9999
    ctype = np.full((ny, nx), fill_int, dtype=np.int32)

    # 地表高度
    if zsfc is None:
        zsfc_arr = np.zeros((ny, nx), dtype=np.float32)
    else:
        zsfc_arr = zsfc.astype(np.float32)

    # 位势高度转几何高度 (向量化)
    ihh = _agri_change_vec(cth)
    # 云顶相对高度 (km)
    height = (ihh - zsfc_arr) / 1000.0

    # 有效性掩码: 所有条件同时满足的像素才参与分类
    valid = (
        np.isfinite(bt14) &
        (vzen < ZEN_MAX) &
        (sunzen < SOLZEN_MAX) &
        (bt14 >= BT14_MIN) & (bt14 <= BT14_MAX) &
        (height > 0.0) &
        np.isfinite(ctt)
    )
    if cod is not None:
        valid = valid & np.isfinite(cod)
    if cer is not None:
        valid = valid & np.isfinite(cer)

    # 没有光学厚度或半径 → 有效像素标记为 0 (无云/缺失)
    if cod is None or cer is None:
        ctype[valid] = 0
        return ctype

    # 提取有效像素参数
    h = height[valid]
    ph = phase[valid]
    rad = cer[valid]
    ot = cod[valid]
    temp = ctt[valid]
    tbb = bt14[valid]
    elev = zsfc_arr[valid]

    # 向量化分类
    result = _classify_vec(h, ph, rad, ot, elev, temp, tbb)
    ctype[valid] = result

    return ctype
