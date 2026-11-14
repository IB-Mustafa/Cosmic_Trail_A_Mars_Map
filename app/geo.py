"""Mars coordinate helpers.

Conventions used throughout COSMIC TRAIL (see ARCHITECTURE.md):

* Geographic coordinates: planetocentric latitude, longitude positive EAST,
  longitudes reported in the range [-180, 180) (Gale Crater is ~137.4 E either way).
* Reference body for map math: sphere of radius 3,396,190 m. This is the
  sphere used by the USGS MOLA 463 m mosaic and by HiRISE DTM map projections,
  so all layers share one consistent reference.
* Local analysis projection: Equidistant Cylindrical (``eqc``) on that sphere,
  with the true-scale latitude and origin placed at the study-area centre.
  Over a few kilometres around the centre, horizontal scale error is far below
  the 5 m analysis cell size (see ``scale_error_at``).

Nothing here uses Earth's WGS84 ellipsoid or Web Mercator.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

MARS_SPHERE_RADIUS_M = 3_396_190.0  # MOLA / HiRISE map-projection sphere
MARS_MEAN_RADIUS_M = 3_389_500.0     # IAU mean radius, reported for comparison only


def proj_string(lat0: float, lon0: float, radius: float = MARS_SPHERE_RADIUS_M) -> str:
    """PROJ definition of the local equidistant-cylindrical analysis CRS."""
    return (
        f"+proj=eqc +lat_ts={lat0:.6f} +lat_0={lat0:.6f} +lon_0={lon0:.6f} "
        f"+x_0=0 +y_0=0 +R={radius:.1f} +units=m +no_defs +type=crs"
    )


@dataclass(frozen=True)
class LocalEqc:
    """Spherical equidistant-cylindrical projection centred on the study area.

    Forward:  x = R * cos(lat0) * (lon - lon0),  y = R * (lat - lat0)   (radians)
    This is exactly PROJ's ``eqc`` with lat_ts = lat_0 = lat0 on a sphere.
    """

    lat0: float
    lon0: float
    radius: float = MARS_SPHERE_RADIUS_M

    @property
    def _k(self) -> float:
        return self.radius * math.cos(math.radians(self.lat0))

    def forward(self, lon: float, lat: float) -> tuple[float, float]:
        dlon = _wrap180(lon - self.lon0)
        return self._k * math.radians(dlon), self.radius * math.radians(lat - self.lat0)

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        lon = self.lon0 + math.degrees(x / self._k)
        lat = self.lat0 + math.degrees(y / self.radius)
        return _wrap180(lon), lat

    def proj(self) -> str:
        return proj_string(self.lat0, self.lon0, self.radius)

    def scale_error_at(self, y: float) -> float:
        """Relative E-W scale error of eqc at northing ``y`` (0 at the centre)."""
        lon, lat = self.inverse(0.0, y)
        return abs(math.cos(math.radians(self.lat0)) / math.cos(math.radians(lat)) - 1.0)


def _wrap180(lon: float) -> float:
    return ((lon + 180.0) % 360.0) - 180.0


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float,
                radius: float = MARS_SPHERE_RADIUS_M) -> float:
    """Great-circle distance on a Mars sphere (metres)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(_wrap180(lon2 - lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def validate_lonlat(lon: float, lat: float) -> None:
    if not (isinstance(lon, (int, float)) and isinstance(lat, (int, float))):
        raise ValueError("Coordinates must be numbers.")
    if not (math.isfinite(lon) and math.isfinite(lat)):
        raise ValueError("Coordinates must be finite numbers.")
    if not -90.0 <= lat <= 90.0:
        raise ValueError("Latitude must be between -90 and 90 degrees.")
    if not -360.0 <= lon <= 360.0:
        raise ValueError("Longitude must be between -360 and 360 degrees.")
