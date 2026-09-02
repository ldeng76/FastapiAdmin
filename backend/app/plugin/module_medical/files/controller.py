"""医疗文件 — API 控制器。

自动发现挂载到 /medical/files/*。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path as FastPath, Query
from fastapi.responses import FileResponse, JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ResponseSchema, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import (
    MedFilesDictOutSchema,
    MedFilesStatisticsOutSchema,
    MedicalFilesQueryParam,
)
from .service import MedFilesService

MedFilesRouter = APIRouter(
    route_class=OperationLogRoute, prefix="/files", tags=["医疗文件"],
)


@MedFilesRouter.get(
    "/list",
    summary="查询医疗文件列表",
    response_model=ResponseSchema[dict],
)
async def list_med_files_controller(
    search: Annotated[MedicalFilesQueryParam, Depends()],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:files:query"]))],
    page_no: Annotated[int, Query(ge=1, description="当前页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页数量")] = 30,
) -> JSONResponse:
    """分页查询医疗文件列表。

    - exam_type：模态类型，多选逗号分隔（如 ?exam_type=CT,PETCT），为空返回全部
    - file_type：文件类型，多选逗号分隔（如 ?file_type=dicom,nii），为空返回全部
    """
    exam_type = search.exam_type[1] if search.exam_type else None
    file_type = search.file_type[1] if search.file_type else None
    result = await MedFilesService.page_service(
        auth=auth,
        offset=(page_no - 1) * page_size,
        limit=page_size,
        order_by=[{"id": "desc"}],
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
