from math import atan2, cos, radians, sin, sqrt


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in meters between two coordinates."""
    radius_m = 6371000
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    delta_phi = radians(lat2 - lat1)
    delta_lambda = radians(lon2 - lon1)

    a = sin(delta_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return radius_m * c

