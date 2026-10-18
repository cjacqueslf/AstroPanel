import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from datetime import datetime, timezone, timedelta
import pytest
from PySide6.QtWidgets import QApplication
from astropanel.services.seeing import parse_forecast, forecast_url
from astropanel.domain.models import ObservatoryLocation, AppSettings
from astropanel.ui.seeing import SeeingPanel


def payload():
    return dict(product='astro', init=datetime.now(timezone.utc).strftime('%Y%m%d%H'),
                dataseries=[dict(timepoint=3, seeing=2, cloudcover=8, transparency=6, prec_type='rain'),
                            dict(timepoint=6, seeing=7, cloudcover=1, transparency=1, prec_type='none')])


def test_parse_utc_and_categories():
    issued, rows = parse_forecast(payload())
    assert issued.tzinfo == timezone.utc
    assert rows[0].time == issued + timedelta(hours=3)
    assert rows[0].seeing_text == '0,5–0,75″'
    assert rows[0].quality == 'Excelente'
    assert rows[0].rain
    assert rows[1].quality == 'Ruim'
    for category in (0, 9, '2', True):
        data = payload(); data['dataseries'][0]['seeing'] = category
        with pytest.raises(ValueError):
            parse_forecast(data)
    with pytest.raises(ValueError):
        parse_forecast(dict(product='astro', init='2026101200', dataseries=[]))
    assert 'lat=-23.5505' in forecast_url(ObservatoryLocation())


def test_panel_location_render_and_expiry(monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []
    monkeypatch.setattr(SeeingPanel, 'refresh_forecast', lambda self: calls.append(self.location))
    panel = SeeingPanel()
    location = ObservatoryLocation('Casa')
    panel.set_location(location, True)
    assert calls == [location]
    panel.set_location(location, True)
    panel.issued, panel.samples = parse_forecast(payload())
    panel.received = datetime.now(timezone.utc)
    panel.render_forecast()
    assert panel.table.rowCount() == 2
    assert 'Excelente' in panel.summary.text()
    assert 'precip.' in panel.table.item(0, 2).text()
    assert panel.table.item(0, 0).text() == panel.samples[0].time.astimezone(panel.zone).strftime('%d/%m %H:%M')
    panel.issued -= timedelta(days=5)
    from dataclasses import replace
    panel.samples = [replace(sample, time=sample.time - timedelta(days=5)) for sample in panel.samples]
    panel.render_forecast()
    assert panel.table.rowCount() == 0
    assert 'ANTIGA' in panel.status.text()
    panel.set_location(ObservatoryLocation('Campo', -20), False)
    assert panel.samples == []
    assert not panel.timer.isActive()
    assert AppSettings(visible_panels=['seeing']).visible_panels == ['seeing']
    panel.close()
