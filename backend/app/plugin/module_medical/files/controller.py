"""医疗文件 — API 控制器。

自动发现挂载到 /medical/files/*。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path as FastPath, Query, status
from fastapi.responses import FileResponse, JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission
from app.core.exceptions import CustomException
from app.core.router_class import OperationLogRoute

from .schema import (
    FileExistenceOutSchema,
    MedFilesDictOutSchema,
    MedFilesStatisticsOutSchema,
    MedicalFilesQueryParam,
)
from .service import MedFilesService

MedFilesRouter = APIRouter(
    route_class=OperationLogRoute, prefix="/files", tags=["医疗文件"],
)

# 允许排序的字段白名单（对应 MedFilesModel 的 ORM 属性名，防止注入任意列）
ALLOWED_SORT_FIELDS = {
    "id", "anon_exam_id", "file_name", "patient_id",
    "exam_type", "file_type", "file_path",
}
# 允许的排序方式
ALLOWED_SORT_ORDERS = {"asc", "desc"}


def _normalize_order_by(raw: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """把 PaginationQueryParam 传入的 order_by 过滤到白名单内。

    非法字段/方向会被静默跳过；全部被过滤时回退到默认 [{"id": "desc"}]。
    """
    if not raw:
        return [{"id": "desc"}]
    result: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        for field, direction in item.items():
            if field not in ALLOWED_SORT_FIELDS:
                continue
            direction = str(direction).lower()
            if direction not in ALLOWED_SORT_ORDERS:
                continue
            result.append({field: direction})
    return result or [{"id": "desc"}]


@MedFilesRouter.get(
    "/list",
    summary="查询医疗文件列表",
    response_model=ResponseSchema[dict],
)
async def list_med_files_controller(
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[MedicalFilesQueryParam, Depends()],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:files:query"]))],
) -> JSONResponse:
    """分页查询医疗文件列表。

    - exam_type：模态类型，多选逗号分隔（如 ?exam_type=CT,PETCT），为空返回全部
    - file_type：文件类型，多选逗号分隔（如 ?file_type=dicom,nii），为空返回全部
    - order_by：排序，JSON 数组，如 [{"patient_id":"asc"},{"id":"desc"}]
    """
    exam_type = search.exam_type[1] if search.exam_type else None
    file_type = search.file_type[1] if search.file_type else None
    order_by = _normalize_order_by(page.order_by)
    result = await MedFilesService.page_service(
        auth=auth,
        offset=page.offset,
        limit=page.limit,
        order_by=order_by,
        exam_type=exam_type,
        file_type=file_type,
    )
    return SuccessResponse(data=result, msg="查询医疗文件列表成功")


@MedFilesRouter.get(
    "/dict/file-types",
    summary="文件类型字典（根据已有数据）",
    response_model=ResponseSchema[MedFilesDictOutSchema],
)
async def dict_file_types_controller(
    search: Annotated[MedicalFilesQueryParam, Depends()],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:files:query"]))],
) -> JSONResponse:
    """返回当前数据库实际出现过的 file_type 字典。

    若传 `exam_type`，只会统计指定模态类型下实际存在的文件类型。
    结果已做行级权限过滤（与 `/list` 一致的数据可见性）。
    """
    exam_type = search.exam_type[1] if search.exam_type else None
    data = await MedFilesService.dict_file_types_service(auth=auth, exam_type=exam_type)
    return SuccessResponse(data=data, msg="查询文件类型字典成功")


@MedFilesRouter.get(
    "/statistics",
    summary="医疗文件统计（文件数 / 患者数 / 总大小）",
    response_model=ResponseSchema[MedFilesStatisticsOutSchema],
)
async def statistics_controller(
    search: Annotated[MedicalFilesQueryParam, Depends()],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:files:query"]))],
) -> JSONResponse:
    """统计满足筛选条件的：文件个数、患者数（去重）、所有文件总大小。

    - exam_type：模态类型，多选逗号分隔（如 ?exam_type=CT,PETCT）
    - file_type：文件类型，多选逗号分隔（如 ?file_type=dicom,nii）
    """
    exam_type = search.exam_type[1] if search.exam_type else None
    file_type = search.file_type[1] if search.file_type else None
    data = await MedFilesService.statistics_service(
        auth=auth, exam_type=exam_type, file_type=file_type
    )
    return SuccessResponse(data=data, msg="查询医疗文件统计成功")


@MedFilesRouter.get(
    "/stream/{file_id}",
    summary="查询附件流",
    response_class=FileResponse,
)
async def get_file_stream_controller(
    file_id: Annotated[int, FastPath(description="文件ID", ge=1)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:files:query"]))],
) -> FileResponse:
    """按文件ID返回附件二进制流。"""
    path, file_name = await MedFilesService.get_file_stream_service(
        auth=auth, file_id=file_id
    )
    return FileResponse(
        path=str(path),
        filename=file_name,
        media_type="application/octet-stream",
    )


@MedFilesRouter.get(
    "/study-uid/{file_id}",
    summary="按文件ID获取 StudyInstanceUID",
    response_model=ResponseSchema[str],
)
async def get_study_instance_uid_controller(
    file_id: Annotated[int, FastPath(description="文件ID", ge=1)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:files:query"]))],
) -> JSONResponse:
    """按文件ID读取 DICOM 文件并返回 StudyInstanceUID。"""
    uid = await MedFilesService.get_study_instance_uid_service(
        auth=auth, file_id=file_id
    )
    return SuccessResponse(data=uid, msg="获取 StudyInstanceUID 成功")


@MedFilesRouter.get(
    "/check-exists",
    summary="校验文件是否存在（file_id / anon_exam_id 二选一）",
    response_model=ResponseSchema[FileExistenceOutSchema],
)
async def check_file_exists_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:files:query"]))],
    file_id: Annotated[
        int | None, Query(description="文件主键 study_key；与 anon_exam_id 二选一")
    ] = None,
    anon_exam_id: Annotated[
        str | None, Query(description="脱敏检查ID；与 file_id 二选一")
    ] = None,
) -> JSONResponse:
    """按 file_id 或 anon_exam_id 校验磁盘文件是否实际存在。

    两个参数必须且只能传一个；返回值不会抛异常（记录不存在也算 exists=False）。
    """
    if file_id is None and not anon_exam_id:
        raise CustomException(
            msg="file_id 与 anon_exam_id 必须传一个",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if file_id is not None and anon_exam_id:
        raise CustomException(
            msg="file_id 与 anon_exam_id 只能传一个",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    data = await MedFilesService.check_file_existence_service(
        auth=auth, file_id=file_id, anon_exam_id=anon_exam_id,
    )
    return SuccessResponse(data=data, msg="校验文件存在性成功")
