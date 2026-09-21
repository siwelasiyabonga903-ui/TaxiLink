import json

from urllib.error import (
    HTTPError,
    URLError,
)
from urllib.request import (
    Request,
    urlopen,
)

from django.conf import settings


DIRECTIONS_URL = (
    "https://api.heigit.org/"
    "openrouteservice/v2/directions/"
    "driving-car/geojson"
)


class RoutingServiceError(Exception):
    pass


def get_route_geojson(route):
    api_key = (
        settings.OPENROUTESERVICE_API_KEY
    )

    if not api_key:
        raise RoutingServiceError(
            "OpenRouteService API key "
            "is not configured."
        )

    waiting_spots = list(
        route.waiting_spots
        .filter(
            is_active=True
        )
        .order_by(
            "stop_order",
            "id",
        )
    )

    if len(waiting_spots) < 2:
        raise RoutingServiceError(
            "At least two active waiting spots "
            "are required to generate a road route."
        )

    coordinates = [
        [
            float(
                waiting_spot.longitude
            ),
            float(
                waiting_spot.latitude
            ),
        ]
        for waiting_spot
        in waiting_spots
    ]

    body = json.dumps(
        {
            "coordinates": coordinates,
        }
    ).encode(
        "utf-8"
    )

    request = Request(
        DIRECTIONS_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": api_key,
            "Content-Type": (
                "application/json"
            ),
            "Accept": (
                "application/geo+json"
            ),
        },
    )

    try:
        with urlopen(
            request,
            timeout=15,
        ) as response:
            result = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except HTTPError as exc:
        try:
            details = (
                exc.read()
                .decode("utf-8")
            )
        except Exception:
            details = ""

        raise RoutingServiceError(
            f"Routing service returned "
            f"HTTP {exc.code}. "
            f"{details}"
        ) from exc

    except (URLError, TimeoutError) as exc:
        raise RoutingServiceError(
            "Could not connect to the "
            "routing service."
        ) from exc

    except json.JSONDecodeError as exc:
        raise RoutingServiceError(
            "Routing service returned "
            "an invalid response."
        ) from exc

    if not isinstance(result, dict):
        raise RoutingServiceError(
            "Routing service returned "
            "an invalid response."
        )

    if not result.get("features"):
        raise RoutingServiceError(
            "Routing service did not "
            "return a road route."
        )

    return result


def get_coordinates_geojson(
    coordinates,
):
    api_key = (
        settings.OPENROUTESERVICE_API_KEY
    )

    if not api_key:
        raise RoutingServiceError(
            "OpenRouteService API key "
            "is not configured."
        )

    if len(coordinates) < 2:
        raise RoutingServiceError(
            "At least two coordinates "
            "are required to generate "
            "a road route."
        )

    body = json.dumps(
        {
            "coordinates": coordinates,
        }
    ).encode(
        "utf-8"
    )

    request = Request(
        DIRECTIONS_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": api_key,
            "Content-Type": (
                "application/json"
            ),
            "Accept": (
                "application/geo+json"
            ),
        },
    )

    try:
        with urlopen(
            request,
            timeout=15,
        ) as response:
            result = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except HTTPError as exc:
        try:
            details = (
                exc.read()
                .decode("utf-8")
            )
        except Exception:
            details = ""

        raise RoutingServiceError(
            f"Routing service returned "
            f"HTTP {exc.code}. "
            f"{details}"
        ) from exc

    except (URLError, TimeoutError) as exc:
        raise RoutingServiceError(
            "Could not connect to the "
            "routing service."
        ) from exc

    except json.JSONDecodeError as exc:
        raise RoutingServiceError(
            "Routing service returned "
            "an invalid response."
        ) from exc

    if not isinstance(result, dict):
        raise RoutingServiceError(
            "Routing service returned "
            "an invalid response."
        )

    if not result.get("features"):
        raise RoutingServiceError(
            "Routing service did not "
            "return a road route."
        )

    return result