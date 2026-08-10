"""NIfTI 医学影像服务。

提供 NIfTI 文件的读取和验证功能。
"""

from pathlib import Path

from fastapi import HTTPException, status
from loguru import logger

log = logger.bind(module="nifti")

# 支持的 NIfTI 文件扩展名
NIFTI_EXTENSIONS = {".nii", ".nii.gz", ".hdr", ".img"}


class NIfTIService:
    """NIfTI 医学影像服务。"""

    @staticmethod
    def _validate_path(file_path: str) -> Path:
        """验证并解析文件路径。

        Args:
            file_path: 文件路径

        Returns:
            Path 对象

        Raises:
            HTTPException: 路径无效或文件不存在
        """
        # 安全检查：防止路径遍历攻击
        path = Path(file_path).resolve()

        # 检查是否存在
        if not path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"文件不存在: {file_path}",
            )

        # 检查是否为文件
        if not path.is_file():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"路径不是文件: {file_path}",
            )

        # 检查扩展名
        suffix = path.suffix.lower()
        if suffix == ".gz":
            # .nii.gz 情况
            if path.stem.lower().endswith(".nii"):
                pass
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"不支持的文件格式: {file_path}，仅支持 .nii, .nii.gz",
                )
        elif suffix not in NIFTI_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的文件格式: {file_path}，仅支持 .nii, .nii.gz",
            )

        return path

    @classmethod
    def read_file(cls, file_path: str) -> bytes:
        """读取 NIfTI 文件内容。

        Args:
            file_path: 文件路径

        Returns:
            文件内容 (bytes)

        Raises:
            HTTPException: 读取失败
        """
        path = cls._validate_path(file_path)

        try:
            log.info(f"读取 NIfTI 文件: {path}")
            content = path.read_bytes()
            log.info(f"文件大小: {len(content)} bytes")
            return content
        except Exception as e:
            log.error(f"读取文件失败: {path}, 错误: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"读取文件失败: {str(e)}",
            )

    @classmethod
    def get_file_info(cls, file_path: str) -> dict:
        """获取 NIfTI 文件信息。

        Args:
            file_path: 文件路径

        Returns:
            文件信息字典
        """
        path = cls._validate_path(file_path)

        return {
            "file_path": str(path),
            "file_name": path.name,
            "file_size": path.stat().st_size,
            "modified_time": path.stat().st_mtime,
            "extension": path.suffix.lower(),
        }
