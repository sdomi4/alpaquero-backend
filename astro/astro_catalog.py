from skyfield.api import load, wgs84
from datetime import datetime, timezone

# Load the ephemeris data
ts = load.timescale()
planets = load('de421.bsp')
earth = planets['earth']
moon = planets['moon']
sun = planets['sun']
# Sonnenturm location:
sonnenturm = earth + wgs84.latlon(latitude_degrees=46.85472, longitude_degrees=7.45389, elevation_m=985.5)



def get_sun_position():
    now = datetime.now(timezone.utc)
    t = ts.from_datetime(now)

    astrometric = sonnenturm.at(t).observe(sun)
    ra, dec, distance = astrometric.apparent().radec(epoch='date')
    return {
        "ra": ra.hours,
        "dec": dec.degrees,
        "distance": distance.km
    }

def get_moon_position():
    now = datetime.now(timezone.utc)
    t = ts.from_datetime(now)

    astrometric = sonnenturm.at(t).observe(moon)
    ra, dec, distance = astrometric.apparent().radec(epoch='date')
    return {
        "ra": ra.hours,
        "dec": dec.degrees,
        "distance": distance.km
    }