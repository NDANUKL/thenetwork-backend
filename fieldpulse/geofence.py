"""Shared site radius for arrival and captured evidence checks."""
# Testing allowance disabled: use configured site radii, defaulting to 50 metres.
TESTING_GEOFENCE_RADIUS_M = 0


def effective_geofence_radius(radius):
    return max(float(radius or 50), TESTING_GEOFENCE_RADIUS_M)
