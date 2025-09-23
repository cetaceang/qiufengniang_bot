from datetime import datetime, timedelta, timezone

# 定义北京时区
BEIJING_TZ = timezone(timedelta(hours=8))

def get_start_of_today_utc(tz: timezone = BEIJING_TZ) -> datetime:
    """
    获取指定时区今天开始时间的 UTC datetime 对象。

    :param tz: 目标时区
    :return: 代表指定时区今天零点的 UTC 时间
    """
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(tz)
    start_of_day_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day_local.astimezone(timezone.utc)
    return start_of_day_utc