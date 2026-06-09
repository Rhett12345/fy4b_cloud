# FY-4B AGRI 云产品数据预处理管线

读取 FY-4B 卫星 AGRI 载荷的 L1B 辐射数据和 L2 云产品，按时间配对、定标后输出统一的 NetCDF 文件，供下游云分类算法使用。

## 目录结构

```
fy4b_cloud/
├── plot_cpd.py                        # 可视化脚本（云顶高度/有效半径/云类型三子图）
├── FY4B_cloud_classification/
│   ├── config/
│   │   └── fy4b.yaml                  # 配置文件（目录映射、变量候选、通道定义等）
│   └── scripts/
│       ├── main.py                    # 主入口（调度）
│       ├── config.py                  # 配置加载
│       ├── matcher.py                 # 时间匹配（目录扫描、文件配对）
│       ├── io_l1b.py                  # L1B 读取与标定
│       ├── io_l2.py                   # L2 云产品读取
│       ├── io_geo.py                  # GEO 几何参数读取
│       ├── writer.py                  # NetCDF 输出
│       ├── pack_10_times.sh           # 打包脚本（全分辨率）
│       ├── sync_10_times_to_server.sh # 打包脚本（仅 4km）
│       └── fy4b_cloud_inputs_nc/      # 输出目录
└── FY4BData/
    └── YYYYMMDD/
        └── FY4B_AGRI/
            ├── L1_HDF/DISK/            # L1B 辐射 + 几何（HDF5）
            ├── L2_CLM_DISK/MULT/       # 云检测
            ├── L2_CLP_DISK/MULT/       # 云相态
            ├── L2_CLT_DISK/MULT/       # 云类型
            ├── L2_CTH_DISK/MULT/       # 云顶高度
            ├── L2_CTT_DISK/MULT/       # 云顶温度
            ├── L2_CTP_DISK/MULT/       # 云顶气压
            └── L2_CPD_DISK/MULT/       # 云粒子分布（光学厚度、有效半径、水路径）
```

## 环境依赖

```bash
pip install numpy h5py netCDF4 pyyaml
```

## 使用方法

```bash
cd FY4B_cloud_classification/scripts

python3 main.py \
  --root /path/to/FY4BData/YYYYMMDD/FY4B_AGRI \
  --outdir ./fy4b_cloud_inputs_nc \
  --channels C01,C02,C03,C04,C05,C06,C07,C08,C09,C10,C11,C12,C13,C14 \
  --max-time-diff-min 20
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--root` | 当前机器的 FY4B 数据根目录 | FY4B AGRI 日数据目录 |
| `--outdir` | `./fy4b_cloud_inputs_nc` | 输出 NetCDF 目录 |
| `--channels` | C01~C14 全部 | 逗号分隔的 L1B 通道列表 |
| `--max-time-diff-min` | 配置文件中的值（20） | L1B 与 L2 产品配对的最大时间差（分钟） |
| `--config` | `../config/fy4b.yaml` | YAML 配置文件路径 |

输出文件命名：`FY4B_AGRI_cloud_inputs_YYYYMMDDHHMMSS.nc`，每个时次一个文件。

## 处理流程

```
L1B FDI (HDF5)  ──→  读取 NOMChannel + CALChannel 查找表定标
L1B GEO (HDF5)  ──→  读取卫星/太阳角度
L2 云产品 (NC)  ──→  按候选变量名模糊匹配读取
        ↓
  按 L1B 时间轴，与最近的 L2/GEO 文件配对
        ↓
  输出统一 NetCDF4（zlib 压缩，level 4）
```

## 输出变量说明

每个 .nc 文件包含 31 个变量，图像尺寸 2748×2748（4km 分辨率全盘）。

### L2 云产品

| 变量 | 类型 | 单位 | 编码规则 |
|---|---|---|---|
| `cloud_mask` | int32 | — | 0:云, 1:可能云, 2:可能晴, 3:晴, 126:太空 |
| `cloud_phase` | int32 | — | 0:晴, 1:水云, 2:过冷云, 3:混合云, 4:冰云, 5:不确定 |
| `cloud_type` | int32 | — | 0:晴, 2:水云, 3:过冷, 4:混合, 5:冰, 6:卷云, 7:重叠 |
| `cloud_top_height` | float32 | m | 有效范围 1~20000 |
| `cloud_top_temperature` | float32 | K | 有效范围 160~320 |
| `cloud_top_pressure` | float32 | hPa | 有效范围 1~1100 |
| `cloud_effective_radius` | float32 | μm | 云粒子有效半径 |
| `cloud_type_ii` | int32 | — | 云类型 II 分类（0:晴, 1:层云/层积云, 2:高层云/高积云, 3:积云, 4:卷云, 5:雨层云, 6:积雨云, 7:低层云, 8:高层积云, 61~63:多层云） |
| `Cloud_Height_Class` | uint8 | category | 云顶高度分类（0:晴空, 1:低云 CTH<3km, 2:中云 3≤CTH<6km, 3:高云 CTH≥6km, 255:填充值） |

### GEO 几何角度（float32, 单位: degree）

| 变量 | 说明 | 有效范围 |
|---|---|---|
| `satellite_zenith` | 卫星天顶角 | 0~180 |
| `satellite_azimuth` | 卫星方位角 | 0~360 |
| `sun_zenith` | 太阳天顶角 | 0~180 |
| `sun_azimuth` | 太阳方位角 | 0~360 |
| `sun_glint_angle` | 太阳耀斑角 | -360~360 |
| `column_number` | 列号 | 0~2747 |
| `line_number` | 行号 | 0~2747 |

### L1B 通道（float32，物理值直接存储）

| 变量 | 类型 | 单位 | 说明 |
|---|---|---|---|
| `l1b_C01` ~ `l1b_C06` | float32 | 1（反射率） | 直接为 0~1 的反射率值 |
| `l1b_C07` ~ `l1b_C14` | float32 | K（亮温） | 直接为亮温值 |

填充值：所有变量统一为 -9999（NaN 替换）。

## 定标逻辑

L1B 使用查找表定标（`io_l1b.read_l1b_channels`）：

- `NOMChannelXX`：原始数字码值（二维图像）
- `CALChannelXX`：一维定标查找表
- 物理值 = `CALChannelXX[NOMChannelXX]`，直接输出 float32
- C01-C06（可见光/近红外）：反射率，值域 0~1
- C07-C14（红外）：亮温，单位 K
- 无效码值范围：`NOMChannelXX` 中 > 0 且 < nom_max（C07 为 65534，其余为 4096）
- 无效像素存储为 NaN（NetCDF 中显示为 fill_value -9999）

配置项在 `config/fy4b.yaml` 中的 `channels` 部分，可修改 nom_max、units 等参数。

## 数据打包与传输

```bash
# 打包代码 + 10 个时次数据（全分辨率）
bash pack_10_times.sh

# 打包代码 + 10 个时次数据（仅 4km 分辨率，排除 0500M/1000M/2000M）
bash sync_10_times_to_server.sh
```

打包脚本中路径硬编码为 `/home/hf/`，在其他机器上运行前需修改。

## 典型数据统计（2026-05-13 00:00 时次）

| 变量 | 有效像素 | 最小 | 最大 | 均值 |
|---|---|---|---|---|
| cloud_mask | 7,551,452 | 0 | 126 | 30.3 |
| cloud_phase | 5,784,544 | 0 | 4 | 1.51 |
| cloud_type | 5,784,544 | 0 | 7 | 2.32 |
| cloud_top_height | 3,314,141 | 1 m | 19,954 m | 5,633 m |
| cloud_top_temperature | 3,323,214 | 183 K | 304 K | 259 K |
| cloud_top_pressure | 3,323,021 | 24 hPa | 1,098 hPa | 560 hPa |
| l1b_C01 (反射率) | 5,780,496 | 0.0012 | 1.1130 | 0.0855 |
| l1b_C07 (亮温) | 5,781,940 | 199.99 K | 370.42 K | 284.45 K |
| l1b_C14 (亮温) | 5,784,544 | 182.96 K | 298.86 K | 270.28 K |
