from datetime import date, datetime, timezone

from astropanel.domain.models import ObservatoryLocation
from astropanel.services.astronomy import calculate_sun_moon, local_sidereal_time


SAO_PAULO = ObservatoryLocation("São Paulo", -23.5505, -46.6333, 760, "America/Sao_Paulo")


def test_lst_is_valid_clock() -> None:
    result = local_sidereal_time(SAO_PAULO, datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc))
    assert len(result) == 8
    hours, minutes, seconds = map(int, result.split(":"))
    assert 0 <= hours < 24 and 0 <= minutes < 60 and 0 <= seconds < 60


def test_sun_moon_data_for_sao_paulo() -> None:
    info = calculate_sun_moon(SAO_PAULO, date(2025, 6, 21))
    assert info.sunrise is not None
    assert info.sunset is not None
    assert info.astro_dusk is not None
    assert info.illumination_percent >= 0


def test_polar_summer_can_have_no_astronomical_night() -> None:
    tromsø = ObservatoryLocation("Tromsø", 69.6492, 18.9553, 0, "Europe/Oslo")
    info = calculate_sun_moon(tromsø, date(2025, 6, 21))
    assert info.astronomical_night is None
