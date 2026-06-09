"""
FY-4B AGRI 云产品可视化（2×2 顶刊论文风格）
四子图布局：
Row 1: (a) 云顶高度  /  (b) 云高分类
Row 2: (c) 云粒子半径 /  (d) 云类型
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import Patch
from netCDF4 import Dataset

# 使用 Matplotlib 默认白底风格，确保学术论文纯白背景
plt.style.use("default")

# ─────────────────────────────────────────────
# 0. 读取数据
# ─────────────────────────────────────────────
FILE = "/data/Data_yuq/fy4b_cloud_inputs_nc/FY4B_AGRI_cloud_inputs_20260513000000.nc"
OUTPNG = "/home/liusy2020/yuq/fy4b_cloud/fy4b_cloud_4panel.png"

ds = Dataset(FILE, "r")


def read_var(ds, name, default_fill=-9999):
    """读取变量并屏蔽填充值与异常负值"""
    var = ds.variables[name]
    data = var[:].astype(np.float32)
    fill = getattr(var, "_FillValue", default_fill)
    data = np.ma.masked_where(data == fill, data)
    data = np.ma.masked_where(data < 0, data)
    return data


# 读取原有产品
cth = read_var(ds, "cloud_top_height")  # m
cer = read_var(ds, "cloud_effective_radius")  # μm
cer = np.ma.masked_where(cer > 100, cer)

ctype = ds.variables["cloud_type_ii"][:].astype(np.float32)
fill_ct = getattr(ds.variables["cloud_type_ii"], "_FillValue", -9999)
ctype = np.ma.masked_where(ctype == fill_ct, ctype)

# 新增：读取云高分类数据 (Cloud_Height_Class)
chc = ds.variables["Cloud_Height_Class"][:].astype(np.float32)
fill_chc = getattr(ds.variables["Cloud_Height_Class"], "_FillValue", 255)
chc = np.ma.masked_where(chc == fill_chc, chc)

ds.close()

# ─────────────────────────────────────────────
# 1. 离散变量的配色与标签 (Nature/Science 风格)
# ─────────────────────────────────────────────
# (B) 云高分类配置：0=晴空, 1=低云, 2=中云, 3=高云
CHC_LABELS = {
    0: ("Clear", "#F2F4F4"),  # 极浅灰
    1: ("Low (<3km)", "#5DADE2"),  # 柔和蓝
    2: ("Mid (3-6km)", "#F4D03F"),  # 柔和黄
    3: ("High (≥6km)", "#EC7063")  # 柔和红
}
chc_codes = sorted(CHC_LABELS.keys())
chc_colors = [CHC_LABELS[c][1] for c in chc_codes]
chc_bounds = [c - 0.5 for c in chc_codes] + [chc_codes[-1] + 0.5]
cmap_chc = mcolors.ListedColormap(chc_colors)
norm_chc = mcolors.BoundaryNorm(boundaries=chc_bounds, ncolors=len(chc_colors))

# (D) 云类型配置
CLOUD_LABELS = {
    0: ("Clear", "#C8E6C9"),
    1: ("ST/SC", "#90CAF9"),
    2: ("AS/AC", "#5C6BC0"),
    3: ("CU", "#FFD54F"),
    4: ("CI", "#E0E0E0"),
    5: ("NS", "#78909C"),
    6: ("CB", "#D32F2F"),
    7: ("ST low", "#B3E5FC"),
    8: ("SC high", "#4FC3F7"),
    61: ("CI+SC/ST", "#AB47BC"),
    62: ("CI+AS/AC", "#7B1FA2"),
    63: ("AS/AC+SC/ST", "#FF8A65"),
}
code_list = sorted(CLOUD_LABELS.keys())
color_list = [CLOUD_LABELS[c][1] for c in code_list]
ct_bounds = [c - 0.5 for c in code_list] + [code_list[-1] + 0.5]
cmap_ct = mcolors.ListedColormap(color_list)
norm_ct = mcolors.BoundaryNorm(boundaries=ct_bounds, ncolors=len(color_list))

# ─────────────────────────────────────────────
# 2. 图像布局与美化函数
# ─────────────────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(15, 13), facecolor="white")

fig.suptitle(
    "FY-4B AGRI Cloud Products | 2026-05-13 00:00 UTC",
    fontsize=16,
    fontweight="bold",
    color="black",
    y=0.97
)


def style_ax(ax, letter, title):
    """标准的顶级期刊子图边框与刻度美化"""
    ax.set_facecolor("white")

    # 调整边框线条
    for sp in ax.spines.values():
        sp.set_edgecolor("black")
        sp.set_linewidth(1.0)

    # 刻度线朝外，符合标准学术规范
    ax.tick_params(
        colors="black",
        labelsize=9,
        direction="out",
        length=4,
        width=0.8
    )

    # Nature 风格组合标题：左边加粗序号，中间常规标题
    ax.set_title(f"({letter})", loc="left", fontsize=12, fontweight="bold", pad=10)
    ax.set_title(title, loc="center", fontsize=12, fontweight="regular", pad=10)

    ax.set_xlabel("Column", fontsize=10, color="black")
    ax.set_ylabel("Line", fontsize=10, color="black")


def add_colorbar(fig, ax, im, label):
    """为连续变量子图添加精致的 Colorbar"""
    cb = fig.colorbar(
        im,
        ax=ax,
        fraction=0.046,
        pad=0.04
    )
    cb.set_label(label, fontsize=10, color="black")
    cb.ax.tick_params(labelsize=9, colors="black", direction="out", length=3)
    cb.outline.set_edgecolor("black")
    cb.outline.set_linewidth(0.8)
    return cb


# ─────────────────────────────────────────────
# (A) Row 1, Col 1: 云顶高度
# ─────────────────────────────────────────────
ax = axes[0, 0]
cth_km = cth / 1000.0

im0 = ax.imshow(
    cth_km,
    origin="upper",
    cmap="plasma",
    vmin=0,
    vmax=20,
    interpolation="nearest"
)
style_ax(ax, "a", "Cloud Top Height")
add_colorbar(fig, ax, im0, "Height (km)")

# ─────────────────────────────────────────────
# (B) Row 1, Col 2: 云高分类 (新增)
# ─────────────────────────────────────────────
ax = axes[0, 1]

im1 = ax.imshow(
    chc,
    origin="upper",
    cmap=cmap_chc,
    norm=norm_chc,
    interpolation="nearest"
)
style_ax(ax, "b", "Cloud Height Class")

# 离散图例
chc_patches = [
    Patch(
        facecolor=CHC_LABELS[c][1],
        edgecolor="black",
        linewidth=0.5,
        label=CHC_LABELS[c][0]
    )
    for c in chc_codes
]
leg1 = ax.legend(
    handles=chc_patches,
    loc="center left",
    bbox_to_anchor=(1.04, 0.5),
    fontsize=9,
    framealpha=1.0,
    facecolor="white",
    edgecolor="black",
    title="Height Class",
    title_fontsize=9.5
)
leg1.get_title().set_fontweight('bold')

# ─────────────────────────────────────────────
# (C) Row 2, Col 1: 云粒子有效半径
# ─────────────────────────────────────────────
ax = axes[1, 0]

im2 = ax.imshow(
    cer,
    origin="upper",
    cmap="YlOrRd",
    vmin=2,
    vmax=60,
    interpolation="nearest"
)
style_ax(ax, "c", "Cloud Effective Radius")
add_colorbar(fig, ax, im2, "Radius (μm)")

# ─────────────────────────────────────────────
# (D) Row 2, Col 2: 云类型
# ─────────────────────────────────────────────
ax = axes[1, 1]

im3 = ax.imshow(
    ctype,
    origin="upper",
    cmap=cmap_ct,
    norm=norm_ct,
    interpolation="nearest"
)
style_ax(ax, "d", "Cloud Type")

# 离散图例
legend_patches = [
    Patch(
        facecolor=CLOUD_LABELS[c][1],
        edgecolor="black",
        linewidth=0.5,
        label=f"{c:2d}  {CLOUD_LABELS[c][0]}"
    )
    for c in code_list
]
leg2 = ax.legend(
    handles=legend_patches,
    loc="center left",
    bbox_to_anchor=(1.04, 0.5),
    fontsize=8,
    framealpha=1.0,
    facecolor="white",
    edgecolor="black",
    title="Cloud Type",
    title_fontsize=9.5
)
leg2.get_title().set_fontweight('bold')

# ─────────────────────────────────────────────
# 3. 底部统计信息
# ─────────────────────────────────────────────
stats_text = (
    f"CTH Mean = {np.ma.mean(cth_km):.2f} km   |   "
    f"CER Mean = {np.ma.mean(cer):.1f} μm   |   "
    f"Valid Pixels = {int(np.ma.count(cth_km)):,}"
)

fig.text(
    0.5,
    0.02,
    stats_text,
    ha="center",
    fontsize=10,
    fontweight="regular",
    color="black"
)

# ─────────────────────────────────────────────
# 4. 保存
# ─────────────────────────────────────────────
# 调整边缘留白，留出底部信息栏和顶部大标题的空间
plt.tight_layout(rect=[0, 0.04, 0.98, 0.94])

plt.savefig(
    OUTPNG,
    dpi=300,
    bbox_inches="tight",
    facecolor="white"
)

plt.close()

print(f"✅ Saved standard 2x2 panel figure: {OUTPNG}")