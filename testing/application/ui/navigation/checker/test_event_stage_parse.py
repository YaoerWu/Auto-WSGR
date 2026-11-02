"""模块功能：验证活动章节标识的解析契约。

直接调用方：项目测试运行器。

直接依赖：pytest、event.stage_push 的章节解析入口。

边界：只验证纯解析，不涉及设备、页面和识别。
"""

from __future__ import annotations

import pytest

from autowsgr.application.controller.event.stage_push import EventMode, parse_stage


@pytest.mark.parametrize(
    ('stage', 'difficulty', 'node'),
    [
        ('EX1', EventMode.NORMAL, 1),
        ('EX6', EventMode.NORMAL, 6),
        ('EX7', EventMode.HARD, 1),
        ('EX12', EventMode.HARD, 6),
        ('E1', EventMode.NORMAL, 1),
        ('E6', EventMode.NORMAL, 6),
        ('H1', EventMode.HARD, 1),
        ('H6', EventMode.HARD, 6),
        ('ex7', EventMode.HARD, 1),
    ],
)
def test_parse_stage_returns_difficulty_and_node(
    stage: str,
    difficulty: EventMode,
    node: int,
) -> None:
    """章节标识解析出难度与落点序号。"""
    result = parse_stage(stage)

    assert result.difficulty is difficulty
    assert result.node == node


@pytest.mark.parametrize('stage', ['', 'EX', 'EX0', 'EX13', 'X1', 'E7', 'H7', 'EE', 'EX1A'])
def test_parse_stage_rejects_invalid_stage(stage: str) -> None:
    """非法标识被拒绝。"""
    with pytest.raises(ValueError, match='章节标识'):
        parse_stage(stage)
