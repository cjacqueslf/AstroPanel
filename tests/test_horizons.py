from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
import pytest
from astropy.time import Time
from PySide6.QtWidgets import QApplication
from astropanel.domain.models import ObservatoryLocation
from astropanel.services.horizons import horizons_command,horizons_url,parse_horizons
from astropanel.services.observation import minute_moments,night_bounds


@pytest.mark.parametrize('text,command',[('433','433;'),('499','499;'),('Marte','499'),
    ('Vênus','299'),('JPL 499','499'),('2024 yr4','DES=2024 YR4;'),
    ('C/2023 A3','DES=C/2023 A3;CAP'),('1P','DES=1P;CAP'),('Eros','Eros')])
def test_designation_commands_are_unambiguous(text,command):
    assert horizons_command(text)==command


@pytest.mark.parametrize('value',['',"433'; QUANTITIES='2'",'433;','*'])
def test_invalid_designations_rejected(value):
    with pytest.raises(ValueError):horizons_command(value)


def test_request_is_topocentric_time_dependent_and_airless():
    query=parse_qs(urlparse(horizons_url('433',ObservatoryLocation(),date(2026,10,18))).query)
    assert query['COMMAND']==["'433;'"]
    assert query['CENTER']==["'coord@399'"]
    assert query['SITE_COORD']==["'-46.6333,-23.5505,0.76'"]
    assert query['START_TIME']==["'2026-10-18 15:00:00'"]
    assert query['STOP_TIME']==["'2026-10-19 15:00:00'"]
    assert query['APPARENT']==["'AIRLESS'"]
    assert query['QUANTITIES']==["'1,4'"]
    assert query['STEP_SIZE']==["'1 m'"]


@pytest.fixture
def payload():
    location=ObservatoryLocation();day=date(2026,10,18)
    moments=minute_moments(location,day)
    julian=Time(list(moments)).jd
    rows=[f'{jd:.9f},*,m,{(350+i/100)%360:.5f},-25.5,180,{30-i/100:.6f},' for i,jd in enumerate(julian)]
    return {'result':'Target body name: 433 Eros (A898 PA) {source: JPL}\n$$SOE\n'+'\n'.join(rows)+'\n$$EOE'},location,day


def test_ephemeris_parsing_keeps_motion_and_coordinate_epoch(payload):
    data,location,day=payload
    result=parse_horizons(data,'433',location,day)
    assert result.name=='433 Eros (A898 PA)'
    assert len(result.moments)==1441
    assert result.ra_degrees[0]!=result.ra_degrees[-1]
    assert result.coordinates_at(result.moments[10])==(350.1,-25.5,result.moments[10])
    assert result.location==location


@pytest.mark.parametrize('body,message',[
    ({'result':'No matches found.'},'Não existe objeto'),
    ({'error':'No matches found','result':''},'Não existe objeto'),
    ({'result':'Matching small-bodies: multiple matches'},'ambígua'),
    ({'error':'Date outside valid range','result':''},'não retornou efemérides')])
def test_not_found_ambiguity_and_date_errors_are_distinct(body,message):
    with pytest.raises(ValueError,match=message):parse_horizons(body,'bad',ObservatoryLocation(),date(2026,10,18))


def test_incomplete_ephemeris_is_rejected(payload):
    data,location,day=payload
    data={'result':data['result'].replace('$$EOE','').splitlines()[0]+'\n$$SOE\n1,*,m,1,2,3,4,\n$$EOE'}
    with pytest.raises(ValueError):parse_horizons(data,'433',location,day)


def test_solar_dialog_disables_plot_when_query_changes_or_is_missing(payload):
    from astropanel.ui.object_altitude import SolarSystemDialog
    app=QApplication.instance() or QApplication([])
    data,location,day=payload
    target=parse_horizons(data,'433',location,day)
    dialog=SolarSystemDialog((location,day),target)
    assert dialog.plot.isEnabled()
    assert 'AR' in dialog.coordinates.text()
    assert 'Melhor horário' in dialog.plan_label.text()
    dialog._edited()
    assert dialog.target is None and not dialog.plot.isEnabled()
    dialog._failed('Não existe objeto com essa designação no JPL Horizons.')
    assert 'Não existe' in dialog.status.text()
    assert not dialog.coordinates.text()
    dialog.reject()
