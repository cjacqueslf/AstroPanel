from datetime import date, datetime, timezone
from dataclasses import replace
import math
import pytest
from PySide6.QtWidgets import QApplication
from astropanel.domain.models import ObservatoryLocation
from astropanel.services.deep_sky import (DeepSkyObject, catalog_name, parse_coordinates,
                                          parse_sesame, object_altitude_series)


@pytest.mark.parametrize('text,expected', [('ngc253','NGC 253'),('Messier 31','M 31'),
    ('m031','M 31'),('IC 434','IC 434'),('pgc 002557','PGC 2557'),('NGC 4038A','NGC 4038A')])
def test_catalog_identifiers(text,expected):
    assert catalog_name(text) == expected


@pytest.mark.parametrize('text', ['Vega','NGC','M 0','IC -5','PGC 2;script'])
def test_invalid_identifier(text):
    with pytest.raises(ValueError):catalog_name(text)


def test_coordinates_support_sexagesimal_decimal_and_negative_zero():
    target = parse_coordinates('Custom','12:30:00','-00:30:00')
    assert target.ra_deg == pytest.approx(187.5)
    assert target.dec_deg == pytest.approx(-.5)
    assert parse_coordinates('Custom','12.5','-0.5') == target
    assert target.coordinate_text() == ('12:30:00.00', '-00:30:00.0')


@pytest.mark.parametrize('ra,dec',[('-1','0'),('24','0'),('1','91'),('1','-91'),('nan','0'),('bad','0')])
def test_bad_coordinates(ra,dec):
    with pytest.raises(ValueError):parse_coordinates('Custom',ra,dec)


def test_sesame_result_and_missing_object():
    payload=b'<Sesame><Target><Resolver><INFO>ignored</INFO></Resolver><Resolver><jradeg>10.68470833</jradeg><jdedeg>41.26875</jdedeg></Resolver></Target></Sesame>'
    result = parse_sesame(payload,'M 31')
    assert result.ra_deg == pytest.approx(10.68470833)
    assert result.dec_deg == pytest.approx(41.26875)
    assert result.source == 'CDS/Sesame'
    for invalid in [b'<Sesame><Target><INFO>not found</INFO></Target></Sesame>',b'not XML']:
        with pytest.raises(ValueError):parse_sesame(invalid,'M 999')


def test_object_track_matches_expected_culmination_and_is_offline(monkeypatch):
    monkeypatch.setattr('astropy.utils.iers.iers.download_file',lambda *a,**kw: pytest.fail('Unexpected network'))
    location=ObservatoryLocation()
    target=DeepSkyObject('M 31',10.68470833,41.26875)
    values=object_altitude_series(target,location,date(2026,10,18))
    assert len(values)==97
    assert all(math.isfinite(v) and -90<=v<=90 for v in values)
    expected=90-abs(location.latitude-target.dec_deg)
    assert max(values)==pytest.approx(expected,abs=.5)
    polar=object_altitude_series(DeepSkyObject('North pole',0,90),location,date(2026,10,18))
    assert all(abs(v-location.latitude)<.3 for v in polar)


def test_dialog_plots_custom_and_resolved_coordinates_can_be_edited():
    from astropanel.ui.object_altitude import DeepSkyDialog
    app=QApplication.instance() or QApplication([])
    dialog=DeepSkyDialog()
    dialog.ra.setText('invalid');dialog.dec.setText('-30');dialog.accept()
    assert dialog.target is None
    resolved=DeepSkyObject('NGC 253',11.88805833,-25.2888,'CDS/Sesame')
    dialog._resolved(resolved)
    assert dialog.name.text()=='NGC 253'
    dialog.dec.setText('-30:00:00')
    dialog.accept()
    assert dialog.target.dec_deg==-30
    assert dialog.target.source=='Personalizado'


def test_lunar_and_object_curves_coexist_and_follow_observatory(monkeypatch):
    from astropanel.ui.widgets import MoonAltitudeChart
    from astropanel.ui.object_altitude import ObjectAltitudePanel
    app=QApplication.instance() or QApplication([])
    chart=MoonAltitudeChart();chart.set_values(tuple(range(97)),())
    panel=ObjectAltitudePanel(chart)
    location=ObservatoryLocation()
    panel.set_context(location,date(2026,10,18))
    panel.target=DeepSkyObject('M 31',10.68470833,41.26875)
    panel.refresh_object()
    before=chart.object_altitudes
    assert chart.altitudes==tuple(range(97))
    assert len(before)==97
    panel.set_context(replace(location,latitude=40),date(2026,10,18))
    assert chart.object_altitudes!=before
    panel.resize(620,360)
    assert not panel.grab().isNull()
    panel.clear_object()
    assert not chart.object_altitudes
    assert chart.altitudes==tuple(range(97))
