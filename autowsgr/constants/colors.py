class COLORS:
    """存储一些用于鉴定状态的颜色信息
    所有颜色为 RGB 格式
    """

    CHALLENGE_BLUE = (33, 132, 226)  # 演习界面,挑战按钮的颜色
    SUPPORT_ENABLE = (228, 182, 60)  # 支援启用的黄色
    SUPPORT_DISABLE = (44, 142, 239)  # 支援禁用的蓝色
    SUPPORT_ENLESS = (143, 145, 154)  # 支援次数用尽的灰色
    BLOOD_COLORS = (
        (
            (69, 162, 117),
            (246, 184, 51),
            (
                230,
                58,
                89,
            ),
            (96, 91, 92),
            (43, 87, 112),
        ),
        (
            (70, 182, 88),
            (238, 186, 64),
            (166, 33, 3),
        ),
    )

    """血条的 RGB 格式颜色,[0] 为准备界面,[1] 为战斗结算接界面
        [0]从右到左依次为 [0] 绿色,[1] 黄色,[2] 红色,[3] 黑色,[4] 蓝色
        [1]从左到右依次为 [0] 绿色,[1] 黄色,[2] 红色
    """
