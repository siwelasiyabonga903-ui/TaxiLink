from math import atan2, cos, radians, sin, sqrt


EARTH_RADIUS_METERS = 6_371_000


def calculate_distance_meters(
    latitude_one,
    longitude_one,
    latitude_two,
    longitude_two,
):
    latitude_one = radians(float(latitude_one))
    longitude_one = radians(float(longitude_one))
    latitude_two = radians(float(latitude_two))
    longitude_two = radians(float(longitude_two))

    latitude_difference = latitude_two - latitude_one
    longitude_difference = longitude_two - longitude_one

    haversine_value = (
        sin(latitude_difference / 2) ** 2
        + cos(latitude_one)
        * cos(latitude_two)
        * sin(longitude_difference / 2) ** 2
    )

    central_angle = 2 * atan2(
        sqrt(haversine_value),
        sqrt(1 - haversine_value),
    )

    return EARTH_RADIUS_METERS * central_angle