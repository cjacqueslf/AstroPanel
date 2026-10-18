"""7Timer ASTRO forecast categories; times in the API are UTC."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

SEEING_BANDS = ('<0,5', '0,5–0,75', '0,75–1', '1–1,25', '1,25–1,5', '1,5–2', '2–2,5', '>2,5')
CLOUD_BANDS = ('0–6%', '6–19%', '19–31%', '31–44%', '44–56%', '56–69%', '69–81%', '81–94%', '94–100%')
TRANSPARENCY_BANDS = ('<0,3', '0,3–0,4', '0,4–0,5', '0,5–0,6', '0,6–0,7', '0,7–0,85', '0,85–1', '>1')

@dataclass(frozen=True)
class SeeingSample:
    time: datetime
    seeing: int
    clouds: int
    transparency: int
    rain: bool

    @property
    def seeing_text(self):
        return SEEING_BANDS[self.seeing - 1] + '″'

    @property
    def quality(self):
        return 'Excelente' if self.seeing <= 2 else 'Bom' if self.seeing <= 4 else 'Regular' if self.seeing <= 6 else 'Ruim'

    @property
    def cloud_text(self):
        return CLOUD_BANDS[self.clouds - 1]


def forecast_url(location):
    return 'https://www.7timer.info/bin/api.pl?' + urlencode(dict(
        lat=location.latitude, lon=location.longitude, product='astro', output='json'))


def parse_forecast(payload):
    if not isinstance(payload, dict) or payload.get('product') != 'astro':
        raise ValueError('Produto de previsão inválido')
    issued = datetime.strptime(payload['init'], '%Y%m%d%H').replace(tzinfo=timezone.utc)
    samples = []
    for row in payload['dataseries']:
        seeing, clouds, transparency = row['seeing'], row['cloudcover'], row['transparency']
        hour = row['timepoint']
        if (any(type(value) is not int for value in (seeing, clouds, transparency, hour))
                or not 1 <= seeing <= 8 or not 1 <= clouds <= 9
                or not 1 <= transparency <= 8 or not 0 < hour <= 72):
            raise ValueError('Categoria de previsão inválida')
        samples.append(SeeingSample(issued + timedelta(hours=hour), seeing, clouds,
                                   transparency, row.get('prec_type', 'none') != 'none'))
    if not samples:
        raise ValueError('Previsão vazia')
    return issued, sorted(samples, key=lambda sample: sample.time)
