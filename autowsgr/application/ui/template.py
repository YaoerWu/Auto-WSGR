"""模块功能：加载 UI 层各模块共用的识别模板。

上层调用：
- application.controller 下各识别模块：加载本模块模板。

下层依赖：
- common.vision.adapters.template_matching：按相对路径加载模板。

边界：只做路径拼接与进程内缓存，不解释识别规则、不持有页面状态。
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from autowsgr.common.vision.adapters.template_matching import load_template


if TYPE_CHECKING:
    from autowsgr.common.vision import Template


# UI 层模板根目录，位于 common.vision 的模板根下；namespace 从它起算。
UI_TEMPLATE_ROOT = 'application/ui'


@cache
def load_ui_template(namespace: str, filename: str, *, name: str | None = None) -> Template:
    """加载 UI 层某个命名空间下的模板，并按加载参数缓存。

    模板文件在进程运行期间不变，因此同一组参数只读盘解码一次；重复调用返回同一个
    模板对象，识别重试不会反复读盘。

    Args:
        namespace: 相对 UI 模板根的目录，例如 navigation/checker/home。
        filename: 命名空间内的模板文件名。
        name: 模板业务名称，用于识别日志和匹配结果；缺省取文件名主干。

    Returns:
        已加载的模板；相同参数重复调用返回同一个对象。
    """
    relative_path = f'{UI_TEMPLATE_ROOT}/{namespace}/{filename}'
    return load_template(relative_path, name=name or Path(filename).stem)


__all__ = ['UI_TEMPLATE_ROOT', 'load_ui_template']
