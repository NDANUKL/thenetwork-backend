"""Shared testing radius for arrival and captured evidence checks."""
# Temporary cross-county testing range; set to 0 to restore configured site radii.
TESTING_GEOFENCE_RADIUS_M = 2_000_000


def effective_geofence_radius(radius):
    return max(float(radius or 50), TESTING_GEOFENCE_RADIUS_M)
