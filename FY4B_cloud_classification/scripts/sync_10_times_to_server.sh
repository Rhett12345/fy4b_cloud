cat > /home/hf/FY4B_cloud_classification/scripts/pack_10_times.sh <<'EOF'
#!/bin/bash
set -euo pipefail

# =========================================================
# 本地路径
# =========================================================
PROJECT_DIR="/home/hf/FY4B_cloud_classification"
DATA_ROOT="/home/hf/FY4BData/20260513/FY4B_AGRI"

PACK_DIR="/home/hf/FY4B_transfer_10times"
TAR_FILE="/home/hf/FY4B_cloud_classification_10times.tar.gz"

# =========================================================
# 10 个时刻
# =========================================================
TIMES=(
  "20260513000000"
  "20260513001500"
  "20260513003000"
  "20260513004500"
  "20260513010000"
  "20260513011500"
  "20260513013000"
  "20260513014500"
  "20260513020000"
  "20260513021500"
)

# =========================================================
# 需要的产品
# L1_HDF 里面会同时拷贝 FDI 和 GEO
# =========================================================
PRODUCT_DIRS=(
  "L1_HDF"
  "L2_CLM_DISK"
  "L2_CLP_DISK"
  "L2_CTH_DISK"
  "L2_CTT_DISK"
  "L2_CTP_DISK"
  "L2_CLT_DISK"
)

echo "============================================================"
echo "清理旧打包目录"
echo "============================================================"
rm -rf "${PACK_DIR}"
rm -f "${TAR_FILE}"

mkdir -p "${PACK_DIR}/FY4B_cloud_classification"
mkdir -p "${PACK_DIR}/FY4BData/20260513/FY4B_AGRI"

echo
echo "============================================================"
echo "拷贝程序代码"
echo "============================================================"
rsync -av \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude "output/" \
  --exclude "logs/" \
  "${PROJECT_DIR}/" \
  "${PACK_DIR}/FY4B_cloud_classification/"

echo
echo "============================================================"
echo "拷贝 10 个时刻原始数据"
echo "============================================================"

for product in "${PRODUCT_DIRS[@]}"; do
  LOCAL_PRODUCT_DIR="${DATA_ROOT}/${product}"
  TARGET_PRODUCT_DIR="${PACK_DIR}/FY4BData/20260513/FY4B_AGRI/${product}"

  mkdir -p "${TARGET_PRODUCT_DIR}"

  if [ ! -d "${LOCAL_PRODUCT_DIR}" ]; then
    echo "[WARN] 目录不存在，跳过: ${LOCAL_PRODUCT_DIR}"
    continue
  fi

  echo
  echo ">>> 产品: ${product}"

  for t in "${TIMES[@]}"; do
    echo "  >>> 时刻: ${t}"

    if [ "${product}" = "L1_HDF" ]; then
      # L1_HDF 必须同时包含 FDI 和 GEO
      mapfile -t files < <(find "${LOCAL_PRODUCT_DIR}" -type f \( -name "*L1-_FDI-*${t}*" -o -name "*L1-_GEO-*${t}*" \))
    else
      mapfile -t files < <(find "${LOCAL_PRODUCT_DIR}" -type f -name "*${t}*")
    fi

    if [ "${#files[@]}" -eq 0 ]; then
      echo "    [MISS] 没找到 ${product} ${t}"
      continue
    fi

    for f in "${files[@]}"; do
      rel_path="${f#${LOCAL_PRODUCT_DIR}/}"
      rel_dir="$(dirname "${rel_path}")"

      mkdir -p "${TARGET_PRODUCT_DIR}/${rel_dir}"

      echo "    [COPY] ${f}"
      cp -av "${f}" "${TARGET_PRODUCT_DIR}/${rel_dir}/"
    done
  done
done

echo
echo "============================================================"
echo "检查已拷贝文件数量"
echo "============================================================"
find "${PACK_DIR}" -type f | wc -l
find "${PACK_DIR}/FY4BData/20260513/FY4B_AGRI/L1_HDF" -type f | sort | head -20

echo
echo "============================================================"
echo "开始压缩"
echo "============================================================"
cd /home/hf
tar -czvf "${TAR_FILE}" "$(basename "${PACK_DIR}")"

echo
echo "============================================================"
echo "打包完成"
echo "============================================================"
ls -lh "${TAR_FILE}"
du -h "${TAR_FILE}"

echo
echo "压缩包路径："
echo "${TAR_FILE}"
EOF

chmod +x /home/hf/FY4B_cloud_classification/scripts/pack_10_times.sh