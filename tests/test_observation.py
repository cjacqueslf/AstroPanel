from datetime import date,datetime,timedelta,timezone
from dataclasses import replace
import pytest
from astral import Observer
from astral.sun import elevation
from astropanel.domain.models import ObservatoryLocation
from astropanel.services.astronomy import MoonlessWindow
from astropanel.services.observation import (minute_moments,night_bounds,plan_observation,darkness_intervals,plan_text)


def synthetic():
    start=datetime(2026,10,18,12,tzinfo=timezone.utc)
    moments=tuple(start+timedelta(minutes=i) for i in range(1441))
    heights=tuple(30-abs(i-240)/7 for i in range(1441))
    return start,moments,heights


def test_best_time_is_inside_darkness_even_when_transit_is_in_daylight(monkeypatch):
    start,moments,heights=synthetic()
    begin=start+timedelta(hours=6,seconds=30)
    end=start+timedelta(hours=10)
    monkeypatch.setattr('astropanel.services.observation.darkness_intervals',lambda *a:(MoonlessWindow(begin,end),))
    plan=plan_observation(moments,heights,ObservatoryLocation(),date(2026,10,18))
    assert plan.rises==(start+timedelta(minutes=30),)
    assert plan.sets==(start+timedelta(minutes=450),)
    assert plan.best_time==begin
    assert plan.best_time!=moments[heights.index(max(heights))]
    assert plan.best_altitude>0


def test_best_time_can_be_at_astronomical_dawn(monkeypatch):
    start,moments,_=synthetic()
    heights=tuple(i/100 for i in range(1441))
    end=start+timedelta(hours=10,seconds=30)
    monkeypatch.setattr('astropanel.services.observation.darkness_intervals',lambda *a:(MoonlessWindow(start,end),))
    plan=plan_observation(moments,heights,ObservatoryLocation(),date(2026,10,18))
    assert plan.best_time==end


def test_no_darkness_and_no_visible_target_are_explicit(monkeypatch):
    start,moments,heights=synthetic();location=ObservatoryLocation()
    monkeypatch.setattr('astropanel.services.observation.darkness_intervals',lambda *a:())
    plan=plan_observation(moments,heights,location,date(2026,10,18))
    assert plan.best_time is None and 'Sem noite' in plan.reason
    monkeypatch.setattr('astropanel.services.observation.darkness_intervals',lambda *a:(MoonlessWindow(moments[0],moments[-1]),))
    plan=plan_observation(moments,(-2,)*len(moments),location,date(2026,10,18))
    assert not plan.rises and not plan.sets
    assert plan.best_time is None and 'abaixo do horizonte' in plan.reason
    plan=plan_observation(moments,(20,)*len(moments),location,date(2026,10,18))
    assert 'Sempre acima' in plan.horizon_status
    assert plan.best_altitude==20


def test_real_fixed_object_best_time_has_astronomical_darkness():
    from astropanel.services.deep_sky import DeepSkyObject,object_altitudes_at
    location=ObservatoryLocation();day=date(2026,10,18)
    moments=minute_moments(location,day)
    heights=object_altitudes_at(DeepSkyObject('M 31',10.68470833,41.26875),location,moments)
    plan=plan_observation(moments,heights,location,day)
    assert plan.best_time is not None
    assert plan.best_altitude>0
    observer=Observer(location.latitude,location.longitude,location.altitude_m)
    assert elevation(observer,plan.best_time,with_refraction=False)<-17.99


def test_polar_no_night_and_full_darkness_and_dst():
    location=ObservatoryLocation('Polo',89,0,0,'UTC')
    assert not darkness_intervals(location,date(2026,6,21))
    winter=darkness_intervals(location,date(2026,12,21))
    assert len(winter)==1
    assert winter[0].duration==timedelta(days=1)
    ny=ObservatoryLocation('NY',40.7,-74,0,'America/New_York')
    start,end=night_bounds(ny,date(2026,10,31))
    assert end-start==timedelta(hours=25)
    assert len(minute_moments(ny,date(2026,10,31)))==1501
