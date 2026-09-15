#!/usr/bin/env bash
# =============================================================================
# 一键跑 ETL-2 dicom_series 阶段（方案 B 步骤 2）
#
# 背景：
#   ETL-2 的 dicom_series 阶段（anon_etl_engine._import_dicom_series_for_center）
#   扫描 lnrs_anon_imaging_study.image_path 目录，解析 series 元数据并 upsert
#   到 lnrs_anon_dicom_series（含 byte_size 累加）。
#
# 前置：
#   1. lnrs_anon_dicom_series 表存在（0006-anonymized-schema-lnrs.sql §7）
#   2. lnrs_anon_v_imaging_study_counts 视图存在（0020-imaging-study-counts-view.sql）
#   3. lnrs_anon_imaging_study.anon_exam_id 已回填（见 etl2/backfill_imaging_study_exam_id.py）
#   4. 磁盘 DICOM 目录可访问（/data/wlx/DATABASE/...；h196_3 上 119,350 study × 22-116MB/个）
#
# 用途：
#   - 默认 DRY-RUN：打印将处理的中心 + dicom_series DB-SCAN 分支，不连库写入
#   - --apply：实际跑 ETL-2（10-30 小时；不可中断前请确认备份窗口）
#
# 用法：
#   # 1) dry-run（不修改任何数据）
#   ENVIRONMENT=h196_3 ./run_dicom_series_etl.sh
#
#   # 2) 实际跑全量
#   ENVIRONMENT=h196_3 ./run_dicom_series_etl.sh --apply
#
#   # 3) 仅跑单中心 zhujiang
#   ENVIRONMENT=h196_3 ./run_dicom_series_etl.sh --apply --centers zhujiang
#
#   # 4) 增量补漏：仅扫 dicom_series=0 的 study（重跑场景）
#   ENVIRONMENT=h196_3 ./run_dicom_series_etl.sh --apply --centers zhujiang --incremental
#       （注：增量模式需直接调 anon_etl_engine._import_dicom_series_for_center(scope='unexamined')；
#        本脚本的 --incremental 仅作 hook 提示，未真正切换 spec.scope，见后注）
#
# 预计耗时（h196_3 全量）：
#   - zhujiang（36,356 study）：6-12 小时（磁盘 stat 6-10 TB）
#   - shengyi（82,994 study）：anon_exam_id 回填覆盖率 0.26%（219/82,988 patient），
#     实际 series 落库数极小，可快速跑完
#   - xinqiao / hos301：study 数较小（< 1000）
#
# 回退：
#   - 幂等：ON CONFLICT (dicom_series_uid) DO UPDATE，重跑不会重复落库
#   - 数据回滚：DELETE FROM lnrs_anon_dicom_series WHERE created_batch_id = '<batch>';
#   - 完整回滚：DROP TABLE lnrs_anon_dicom_series + 重跑 0006 + 0020
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 默认值
APPLY=0
CENTERS="zhujiang,shengyi,xinqiao"
INCREMENTAL=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply)
            APPLY=1
            shift
            ;;
        --centers)
            CENTERS="$2"
            shift 2
            ;;
        --incremental)
            INCREMENTAL=1
            shift
            ;;
        -h|--help)
            sed -n '2,40p' "$0"
            exit 0
            ;;
        *)
            echo "未知参数: $1" >&2
            exit 1
            ;;
    esac
done

# 环境检查
if [[ -z "${ENVIRONMENT:-}" ]]; then
    echo "错误: 必须设置 ENVIRONMENT（dev/h196_3/h42）" >&2
    echo "示例: ENVIRONMENT=h196_3 $0 --apply" >&2
    exit 1
fi

echo "============================================================"
echo "  ETL-2 dicom_series 跑库脚本"
echo "============================================================"
echo "  ENVIRONMENT = $ENVIRONMENT"
echo "  centers     = $CENTERS"
echo "  mode        = $([[ $APPLY -eq 1 ]] && echo 'APPLY（实际跑）' || echo 'DRY-RUN（仅打印）')"
echo "  incremental = $([[ $INCREMENTAL -eq 1 ]] && echo 'yes（仅扫 dicom_series=0 的 study）' || echo 'no（全量）')"
echo "  backend dir = $BACKEND_DIR"
echo "============================================================"

# 前置检查：imaging_study.anon_exam_id 回填覆盖率
echo
echo "[前置检查] imaging_study.anon_exam_id 回填覆盖率…"
cd "$BACKEND_DIR"
COVERAGE=$(ENVIRONMENT="$ENVIRONMENT" uv run python ../backend/etl2/backfill_imaging_study_exam_id.py --dry-run 2>&1 \
    | grep -E '^\s+合计' || true)
if [[ -n "$COVERAGE" ]]; then
    echo "  $COVERAGE"
else
    echo "  ⚠️  无法读取覆盖率；请先运行 backfill_imaging_study_exam_id.py --dry-run 验证"
fi

if [[ $APPLY -eq 0 ]]; then
    echo
    echo "[DRY-RUN] 执行 ETL-2 dicom_series dry-run…"
    ENVIRONMENT="$ENVIRONMENT" uv run python -m app.plugin.module_medical.hospital.anon_etl \
        --centers "$CENTERS" --dry-run
    echo
    echo "[DRY-RUN] 完毕。未修改任何数据。"
    exit 0
fi

# 实际跑：需要确认
echo
echo "[APPLY] 即将跑 ETL-2 dicom_series 阶段。"
echo "        预计耗时：6-30 小时；不可中断前请确认备份窗口。"
echo "        回退：DELETE FROM lnrs_anon_dicom_series WHERE created_batch_id = '<batch>';"
echo
read -rp "确认输入 YES 继续: " CONFIRM
if [[ "$CONFIRM" != "YES" ]]; then
    echo "已取消。"
    exit 1
fi

# 增量模式提示（当前未真正切换 spec.scope）
if [[ $INCREMENTAL -eq 1 ]]; then
    echo
    echo "[WARN] --incremental 模式：当前 anon_etl_engine._import_dicom_series_for_center"
    echo "       默认 scope='all'；增量 'unexamined' 需直接调用模块函数。"
    echo "       本脚本暂未切换；如确需增量模式，请改用："
    echo "         uv run python -c \"import asyncio; from app.plugin.module_medical.hospital.anon_etl_engine import _import_dicom_series_for_center; from app.plugin.module_medical.hospital.anon_etl_service import _create_batch, _close_batch; ...\""
    echo
    read -rp "确认按全量 (scope='all') 继续 (YES) / 取消 (其它): " CONFIRM2
    if [[ "$CONFIRM2" != "YES" ]]; then
        echo "已取消。"
        exit 1
    fi
fi

echo
echo "[APPLY] 启动 ETL-2…"
ENVIRONMENT="$ENVIRONMENT" uv run python -m app.plugin.module_medical.hospital.anon_etl \
    --centers "$CENTERS"

echo
echo "[APPLY] 完毕。请检查日志与 lnrs_anon_dicom_series 行数："
echo "        SELECT count(*), sum(byte_size) FROM lnrs_anon_dicom_series;"