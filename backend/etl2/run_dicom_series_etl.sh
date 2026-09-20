#!/usr/bin/env bash
# =============================================================================
# 一键跑 ETL-2 dicom_series 阶段（方案 B 步骤 2；2026-09-15 重构为 study 级 byte_size）
#
# 背景：
#   ETL-2 的 dicom_series 阶段（anon_etl_engine._import_dicom_series_for_center）
#   扫描 lnrs_anon_imaging_study.image_path 目录，对每个 study 目录累加 .dcm 字节数
#   并 upsert 到 lnrs_anon_dicom_series（study 级：1 行 = 1 个 study）。
#
# 2026-09-15 重构：不再调 DicomIndexer.register_folder / pydicom，仅 iterdir + stat。
#   - 原来 series 级（拿 series_uid/modality）需要 pydicom 解析每个 .dcm header，
#     单 study ~300ms；重构后单 study ~30ms（10x 加速）。
#   - 详细影响见 docs/etl2/prd/refactor-impact-dicom-series-study-level.md
#
# 前置：
#   1. lnrs_anon_dicom_series 表存在（study 级 schema；0006-anonymized-schema-lnrs.sql §7）
#   2. lnrs_anon_v_imaging_study_counts 视图存在（0020-imaging-study-counts-view.sql）
#   3. lnrs_anon_imaging_study.anon_exam_id 已回填（见 etl2/backfill_imaging_study_exam_id.py）
#   4. 磁盘 DICOM 目录可访问（/data/wlx/DATABASE/...；h196_3 上 119,350 study × 22-116MB/个）
#
# 用途：
#   - 默认 DRY-RUN：打印将处理的中心 + dicom_series DB-SCAN 分支，不连库写入
#   - --apply：实际跑 ETL-2（重构后预计 zhujiang ~18 分钟；shengyi 0% 覆盖 < 1 分钟）
#   - --allow-null-exam：让 imaging_study.anon_exam_id IS NULL 的 study 仍写 dicom_series 行
#     （anon_exam_id 落 NULL，0024 已允许 FK NULL）。用于「先 series 后 exam」的灌库序列
#     （如 2026-09-19 zhujiang 三盘灌库：B 方案 exam 表 0 行无法做关联）。
#     等价于 export LNRS_DICOM_ALLOW_NULL_EXAM=1 后执行（spec.allow_null_exam > env > 默认）。
#     既有 shengyi 等中心不指定则保持原行为（anon_exam_id NULL 时 skip）—— 重跑结果一致。
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
#   # 5) B 方案（exam 表 0 行无法做关联，allow_null_exam=True 让 dicom_series 仍落库）
#   ENVIRONMENT=h196_3 ./run_dicom_series_etl.sh --apply --centers zhujiang --allow-null-exam
#
#   # 6) Issue 7 修复：--data-root 透传（环境 LNRS_DATA_ROOT 不存在时手动指定）
#   ENVIRONMENT=h196_3 ./run_dicom_series_etl.sh --apply --centers zhujiang --data-root /home/dzy/wk/lnrs/data
#
#   # 7) Issue 7 修复：--dicom-series-only（仅跑 dicom_series spec，batch 标 dicom_dir）
#   ENVIRONMENT=h196_3 ./run_dicom_series_etl.sh --apply --centers zhujiang --dicom-series-only
#
# 回退：
#   - 幂等：ON CONFLICT (dicom_study_uid) DO UPDATE，重跑不会重复落库
#   - 数据回滚：DELETE FROM lnrs_anon_dicom_series WHERE created_batch_id = '<batch>';
#   - 完整回滚：DROP TABLE lnrs_anon_dicom_series + 重跑 0006 §7 (study 级) + 0020
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 默认值
APPLY=0
CENTERS="zhujiang,shengyi,xinqiao"
INCREMENTAL=0
ALLOW_NULL_EXAM=0
DATA_ROOT=""
DICOM_SERIES_ONLY=0
CENTERS_CLI=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply)
            APPLY=1
            shift
            ;;
        --centers)
            CENTERS_CLI="$2"
            shift 2
            ;;
        --incremental)
            INCREMENTAL=1
            shift
            ;;
        --allow-null-exam)
            ALLOW_NULL_EXAM=1
            shift
            ;;
        --data-root)
            DATA_ROOT="$2"
            shift 2
            ;;
        --dicom-series-only)
            DICOM_SERIES_ONLY=1
            shift
            ;;
        -h|--help)
            sed -n '2,60p' "$0"
            exit 0
            ;;
        *)
            echo "未知参数: $1" >&2
            exit 1
            ;;
    esac
done
[[ -n "$CENTERS_CLI" ]] && CENTERS="$CENTERS_CLI"

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
echo "  allow_null_exam = $([[ $ALLOW_NULL_EXAM -eq 1 ]] && echo 'yes（imaging_study.anon_exam_id NULL 也写 dicom_series 行；0024 已允许）' || echo 'no（既有行为：无 exam 关联的 study skip）')"
echo "  backend dir = $BACKEND_DIR"
echo "============================================================"

# 把 ALLOW_NULL_EXAM 透传给引擎（spec.allow_null_exam > env > 默认 False）
# DRY-RUN / APPLY 两条路径都要 export，避免 spec 路径下 spec.allow_null_exam 未设时丢失标志
export LNRS_DICOM_ALLOW_NULL_EXAM="$ALLOW_NULL_EXAM"

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
    # dry-run 也透传 --data-root（避免 /home/dzy/wk/lnrs_dats 不存在时 dry-run 报 exists=False 误导）
    DRY_EXTRA=""
    if [[ -n "$DATA_ROOT" ]]; then
        DRY_EXTRA="--data-root $DATA_ROOT"
    fi
    ENVIRONMENT="$ENVIRONMENT" uv run python -m app.plugin.module_medical.hospital.anon_etl \
        --centers "$CENTERS" --dry-run $DRY_EXTRA
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
# 组装 ETL-2 CLI 参数（Issue 7 修复 Defect 1）：
# - --data-root 把 DATA_ROOT 透传给 anon_etl/__main__.py
#   （环境 LNRS_DATA_ROOT 不存在或临时切根时使用，例如 h196_3 默认
#    /home/dzy/wk/lnrs_dats 缺失 → 用 --data-root /home/dzy/wk/lnrs/data 覆盖）
# - --dicom-series-only 仅跑 dicom_series spec（batch 标 dicom_dir）
EXTRA_ARGS=""
if [[ -n "$DATA_ROOT" ]]; then
    EXTRA_ARGS="$EXTRA_ARGS --data-root $DATA_ROOT"
fi
if [[ $DICOM_SERIES_ONLY -eq 1 ]]; then
    EXTRA_ARGS="$EXTRA_ARGS --dicom-series-only"
fi
ENVIRONMENT="$ENVIRONMENT" uv run python -m app.plugin.module_medical.hospital.anon_etl \
    --centers "$CENTERS" $EXTRA_ARGS