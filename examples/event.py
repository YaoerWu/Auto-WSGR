from autowsgr.fight.event.event20260730 import EventFightPlan
from autowsgr.scripts.main import start_script


timer = start_script('./user_settings.yaml')
# set_support(timer,True) # 如果要在战斗前开启战役支援请取消这一行的注释
plan = EventFightPlan(
    timer,
    plan_path='E1炸鱼',
    fleet_id=2,
)


plan.run_for_times(
    500,
)  # 第一个参数是战斗次数,还有个可选参数为检查远征时间，默认为1800S
