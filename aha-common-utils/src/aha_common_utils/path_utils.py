"""路径工具模块

提供项目路径相关的工具函数，包括：
- 查找项目根目录
- 递归查找 .env 文件
"""
from pathlib import Path


def find_project_root(start_path: Path | None = None) -> Path:
    """查找项目根目录

    通过以下标识识别项目根目录：
    - .git 目录
    - pyproject.toml
    - setup.py
    - requirements.txt

    Args:
        start_path: 开始搜索的路径，默认为当前工作目录

    Returns:
        项目根目录路径
    """
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()
    root_markers = {'.git', 'pyproject.toml', 'setup.py', 'requirements.txt'}

    # 向上查找直到找到根标识或到达文件系统根目录
    while current != current.parent:
        if any((current / marker).exists() for marker in root_markers):
            return current
        current = current.parent

    # 如果没找到，返回起始目录
    return start_path.resolve()


def find_env_files_recursive(
    start_path: Path | None = None,
    env_filename: str = '.env',
) -> list[Path]:
    """递归查找 .env 文件（从根目录到当前目录）

    优先级：项目根目录 < 中间目录 < 当前目录（越接近当前目录优先级越高）

    Args:
        start_path: 当前工作目录，默认为 cwd
        env_filename: 环境变量文件名，默认 '.env'

    Returns:
        .env 文件路径列表，按优先级从低到高排序

    Example:
        >>> # 假设目录结构：
        >>> # /app/.env
        >>> # /app/packages/.env
        >>> # /app/packages/distill-ai/.env
        >>> files = find_env_files_recursive()
        >>> # 返回: ['/app/.env', '/app/packages/.env', '/app/packages/distill-ai/.env']
        >>> # 优先级: 根目录最低 < 中间目录 < 当前目录最高
    """
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()
    root = find_project_root(current)

    # 收集从根目录到当前目录的所有路径
    paths = []
    temp = current
    while temp >= root:
        paths.append(temp)
        if temp == root:
            break
        temp = temp.parent

    # 反转列表，使根目录在前（优先级低）
    paths.reverse()

    # 查找每个路径下的 .env 文件
    env_files = []
    for path in paths:
        env_file = path / env_filename
        if env_file.exists() and env_file.is_file():
            env_files.append(env_file)

    return env_files


__all__ = [
    'find_project_root',
    'find_env_files_recursive',
]
