"""云分类算法模块

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


def _agri_change(cloudtop_hei):
    """位势高度转几何高度

    Args:
        cloudtop_hei: 云顶位势高度 (m)

    Returns:
        几何高度 (m)
    """
    r = 6370856.0
    dh = cloudtop_hei / 10.0
    gi = np.zeros(11)
    for i in range(11):
        hi = i * dh + r
        gi[i] = 9.8 * (r / hi) ** 2
    gm = np.mean(gi)
    return cloudtop_hei * 9.8 / gm


def _classify_pixel(height, phase, radius, opti, elevation, temp, tbb):
    """单个像素的云分类

    Args:
        height: 云顶几何高度 (km)
        phase: 云相态 (1=水, 2=过冷, 3=混合, 4=冰)
        radius: 云有效粒子半径 (um)
        opti: 云光学厚度
        elevation: 地表海拔 (m)
        temp: 云顶温度 (K)
        tbb: 通道14亮温 (K)

    Returns:
        云类型编码 (int)
    """
    # 选择云顶高度阈值
    if elevation >= 3000.0:
        hh = H_TIBET.copy()
    else:
        hh = H_STANDARD.copy()

    # 判断多层云或厚云
    if height > 6.5 and opti > 8.0:
        return _classify_multilayer(opti, tbb, temp, height)
    if opti >= 50.0:
        return _classify_thick(height, radius)

    # 模糊匹配: 比较与4类标准云的距离
    dh = height - hh
    dr = radius - R_STANDARD
    dot = opti - OT_STANDARD

    pdh = 0.5 * np.abs(dh) / height
    pdr = 0.25 * np.abs(dr) / radius
    pdot = 0.25 * np.abs(dot) / opti

    countt = pdh + pdr + pdot
    ik = np.argmin(countt) + 1  # 1-based index

    typee = {1: 1, 2: 2, 3: 3, 4: 4}.get(ik, 4)

    # 第一轮修正
    typee = _refine_round1(typee, height, opti, tbb, temp)
    # 第二轮修正
    typee = _refine_round2(typee, height, opti)
    # 第三轮修正
    typee = _refine_round3(typee, opti, height)
    # 第四轮修正 (最终)
    typee = _refine_final(typee, height, radius, phase, opti, tbb, temp)

    return typee


def _classify_multilayer(opti, tbb, temp, height):
    """多层云分类 (height>6.5 and opti>8.0)"""
    if opti < 19.0:
        return 61  # CI over SC/ST
    dt = tbb - temp
    if dt > 20.0:
        return 61
    if 19.0 <= opti < 40.0:
        return 62  # CI over AS/AC
    if opti >= 40.0 and height < 11.0:
        return 5   # NS
    return 6       # CB


def _classify_thick(height, radius):
    """厚云分类 (opti>=50.0)"""
    if height > 4.0 and radius < 30.0:
        return 5   # NS
    if height > 4.0 and radius >= 30.0:
        return 6   # CB
    return 63      # AS/AC over SC/ST


def _refine_round1(typee, height, opti, tbb, temp):
    """第一轮修正"""
    if typee == 1 and 3.5 < height < 6.0:
        return 2
    if typee == 1 and height >= 6.0:
        return 4
    if typee == 2 and height > 6.0 and opti > 32.0:
        return 6
    if typee == 2 and height < 3.5 and opti < 10.0:
        return 1
    if typee == 2 and height < 2.5:
        return 1
    if typee == 4 and height < 6.0:
        return 2
    return typee


def _refine_round2(typee, height, opti):
    """第二轮修正"""
    if typee == 2 and height > 6.0 and opti <= 8.0:
        return 4
    if typee == 2 and opti < 2.0 and height > 5.5:
        return 4
    if typee == 63 and height < 3.0:
        return 1
    return typee


def _refine_round3(typee, opti, height):
    """第三轮修正"""
    if typee == 61:
        return 62
    if typee == 62 and opti > 24:
        return 5
    if typee == 1 and height <= 1.1:
        return 7
    if typee == 1 and height > 1.1:
        return 8
    if typee == 6 and height < 4.5:
        return 3
    return typee


def _refine_final(typee, height, radius, phase, opti, tbb, temp):
    """最终修正"""
    dt = tbb - temp

    if typee == 6 and radius < 10.0:
        return 5
    if typee == 2 and height <= 3.0 and dt < 2.0:
        return 8
    if typee == 2 and opti > 32.0:
        return 63
    if typee == 5 and height >= 11.0:
        return 6
    if typee == 6 and dt > 15.0:
        return 62
    if typee == 2 and radius > 30.0:
        return 3
    if typee == 8 and radius > 25.0 and phase == 1:
        return 3
    if typee == 7 and radius > 25.0 and phase == 1:
        return 3
    if typee == 3 and opti > 35.0:
        return 6
    if typee == 5 and dt <= 0.0:
        return 6
    if typee == 5 and dt > 20.0:
        return 61
    if typee == 62 and dt > 20.0:
        return 61
    if typee == 8 and opti > 32.0:
        return 3
    if typee == 7 and opti > 32.0:
        return 3
    if typee == 5 and dt <= 0:
        return 6
    if typee == 8 and dt <= -2:
        return 3
    if typee == 7 and dt <= -2:
        return 3
    if typee == 2 and height > 6.0 and opti > 24.0:
        return 6
    if typee == 61 and opti > 24.0:
        return 6
    if typee == 62 and opti > 24:
        return 5
    if typee == 6 and radius < 25.0 and height < 11.0:
        return 5
    if typee == 63 and opti > 42.0:
        return 5
    if typee == 3 and opti > 30.0:
        return 5
    if typee == 8 and opti >= 16.0:
        return 5
    if typee == 7 and opti >= 16.0:
        return 5
    return typee


def run_cloud_classification(l1b_data, l2_data, geo_data, zsfc=None):
    """运行云分类算法

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

    # 位势高度转几何高度 (批量)
    ihh = np.vectorize(_agri_change)(cth)
    # 云顶相对高度 (km)
    height = (ihh - zsfc_arr) / 1000.0

    # 逐像素分类
    for j in range(ny):
        for i in range(nx):
            # 跳过无效像素
            if not np.isfinite(bt14[j, i]):
                continue
            if vzen[j, i] >= ZEN_MAX:
                continue
            if sunzen[j, i] >= SOLZEN_MAX:
                continue
            if bt14[j, i] < BT14_MIN or bt14[j, i] > BT14_MAX:
                continue

            # 缺少光学厚度或半径 → 标记0
            if cod is None or cer is None:
                ctype[j, i] = 0
                continue

            if not np.isfinite(cod[j, i]):
                ctype[j, i] = 0
                continue

            h = height[j, i]
            if h <= 0.0:
                ctype[j, i] = 0
                continue

            ph = phase[j, i]
            rad = cer[j, i]
            ot = cod[j, i]
            temp = ctt[j, i]
            tbb = bt14[j, i]
            elev = zsfc_arr[j, i]

            if not (np.isfinite(rad) and np.isfinite(temp)):
                ctype[j, i] = 0
                continue

            ctype[j, i] = _classify_pixel(h, ph, rad, ot, elev, temp, tbb)

    return ctype
