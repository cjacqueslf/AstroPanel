"""Shared rise/set and best-altitude planning inside astronomical darkness."""
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import math
from zoneinfo import ZoneInfo
from astral import Observer
from astral.sun import elevation
from astropanel.services.astronomy import _below_horizon_intervals


def night_bounds(location, day):
    tz = ZoneInfo(location.timezone)
    start = datetime.combine(day, datetime.min.time(), tzinfo=tz)+timedelta(hours=12)
    end = datetime.combine(day+timedelta(days=1), datetime.min.time(), tzinfo=tz)+timedelta(hours=12)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def minute_moments(location, day):
    start, end = night_bounds(location, day)
    count = int((end-start).total_seconds()//60)
    return tuple(start+timedelta(minutes=i) for i in range(count+1))


def chart_moments(location, day):
    start = datetime.combine(day, datetime.min.time(), tzinfo=ZoneInfo(location.timezone))+timedelta(hours=12)
    return tuple((start+timedelta(minutes=15*i)).astimezone(timezone.utc) for i in range(97))


def interpolate(moments, values, moment):
    index = max(0, min(len(moments)-2, bisect_right(moments, moment)-1))
    span = (moments[index+1]-moments[index]).total_seconds()
    fraction = max(0., min(1., (moment-moments[index]).total_seconds()/span))
    return values[index]*(1-fraction)+values[index+1]*fraction


@lru_cache(maxsize=32)
def darkness_intervals(location, day):
    start, end = night_bounds(location, day)
    observer = Observer(location.latitude, location.longitude, location.altitude_m)
    return _below_horizon_intervals(start, end,
        lambda moment: elevation(observer, moment, with_refraction=False)+18, lambda moment: -1)


@dataclass(frozen=True)
class ObservationPlan:
    rises: tuple
    sets: tuple
    best_time: datetime | None
    best_altitude: float | None
    reason: str
    horizon_status: str
    darkness: tuple


def plan_observation(moments, altitudes, location, day):
    if len(moments) != len(altitudes) or len(moments)<2:
        raise ValueError('Efeméride incompleta para planejar a observação.')
    if any(b<=a for a,b in zip(moments,moments[1:])) or not all(math.isfinite(v) for v in altitudes):
        raise ValueError('Efeméride inválida para planejar a observação.')
    rises, sets = [], []
    for left, right, a, b in zip(moments,moments[1:],altitudes,altitudes[1:]):
        if a<=0<b or a>0>=b:
            crossing = left+(right-left)*(-a/(b-a))
            (rises if b>a else sets).append(crossing)
    dark = darkness_intervals(location, day)
    candidates = []
    for window in dark:
        begin, end = max(window.start,moments[0]), min(window.end,moments[-1])
        if begin>end:
            continue
        candidates.extend((t, h) for t, h in zip(moments,altitudes) if begin<=t<=end and h>0)
        for moment in (begin,end):
            height = interpolate(moments,altitudes,moment)
            if height>0:
                candidates.append((moment,height))
    best = max(candidates,key=lambda value:value[1]) if candidates else None
    reason = '' if best else ('Sem noite astronômica neste intervalo.' if not dark
                              else 'Objeto abaixo do horizonte durante toda a noite astronômica.')
    horizon = 'Sempre acima do horizonte nesta janela.' if min(altitudes)>0 else (
        'Não nasce nesta janela.' if max(altitudes)<=0 else '')
    return ObservationPlan(tuple(rises),tuple(sets),best[0] if best else None,
                           best[1] if best else None,reason,horizon,dark)


def plan_text(plan, location):
    tz = ZoneInfo(location.timezone)
    def times(values):
        return ', '.join(value.astimezone(tz).strftime('%d/%m %H:%M') for value in values) or 'sem evento nesta janela'
    best = (f'{plan.best_time.astimezone(tz):%d/%m %H:%M} (altura {plan.best_altitude:.1f}°)'
            if plan.best_time else plan.reason)
    return (f'Nascer: {times(plan.rises)} · Ocaso: {times(plan.sets)}\n'
            f'Melhor horário na noite astronômica: {best}'
            +(f'\n{plan.horizon_status}' if plan.horizon_status else ''))
