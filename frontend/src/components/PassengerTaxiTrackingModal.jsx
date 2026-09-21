import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { divIcon } from "leaflet";

import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";

import api from "../api/client";


const DEFAULT_MAP_CENTER = [
  -30.5595,
  22.9375,
];


const TAXI_ICON = divIcon({
  className: "",

  html: `
    <div
      style="
        font-size: 30px;
        line-height: 30px;
      "
    >
      🚕
    </div>
  `,

  iconSize: [36, 36],
  iconAnchor: [18, 18],
});


function TrackingViewport({
  driverPosition,
  pickupPositions,
}) {
  const map = useMap();

  const hasAutoFitted =
    useRef(false);

  useEffect(() => {
    if (
      hasAutoFitted.current
      || !driverPosition
      || pickupPositions.length === 0
    ) {
      return;
    }

    map.fitBounds(
      [
        driverPosition,
        ...pickupPositions,
      ],
      {
        padding: [55, 55],
        maxZoom: 16,
      }
    );

    hasAutoFitted.current = true;
  }, [
    map,
    driverPosition,
    pickupPositions,
  ]);

  return null;
}


export default function PassengerTaxiTrackingModal({
  dispatch,
  waitingRequest,
  onClose,
}) {
  const [
    pickupSpots,
    setPickupSpots,
  ] = useState([]);

  const [
    roadGeoJson,
    setRoadGeoJson,
  ] = useState(null);

  const [
    routeVersion,
    setRouteVersion,
  ] = useState(0);

  const [
    driverLocation,
    setDriverLocation,
  ] = useState(null);

const locationInFlight = useRef(false);
const routeInFlight = useRef(false);

const rememberDriverLocation = useCallback((next) => {
  if (!next) return;

  setDriverLocation((current) => {
    const currentTime = Date.parse(
      current?.updated_at ?? ""
    );
    const nextTime = Date.parse(
      next.updated_at ?? ""
    );

    if (
      current
      && Number.isFinite(currentTime)
      && (
        !Number.isFinite(nextTime)
        || nextTime <= currentTime
      )
    ) {
      return current;
    }

    return next;
  });
}, []);

  const [loading, setLoading] =
    useState(true);

  const [locationError, setLocationError] = useState("");
  const [routeError, setRouteError] = useState("");

  const error = [locationError, routeError]
    .filter(Boolean)
    .join(" ");

const loadDriverLocation = useCallback(
  async (silent = false) => {
    if (locationInFlight.current) return;
    locationInFlight.current = true;

    if (!silent) {
      setLoading(true);
    }

    try {
      const response = await api.get(
        `/transport/dispatches/${dispatch.id}/location/`
      );

      if (response.data.available) {
        rememberDriverLocation(response.data);
      }

      setLocationError("");
    } catch (requestError) {
      const responseStatus =
        requestError.response?.status;

      if ([400, 403, 404].includes(responseStatus)) {
        onClose();
        return;
      }

      setLocationError(
        "Taxi location could not be refreshed. Retrying automatically."
      );
    } finally {
      locationInFlight.current = false;

      if (!silent) {
        setLoading(false);
      }
    }
  },
  [dispatch.id, onClose, rememberDriverLocation]
);

const loadPickupRoute = useCallback(
  async () => {
    if (routeInFlight.current) return;
    routeInFlight.current = true;

    try {
      const response = await api.get(
        `/transport/dispatches/${dispatch.id}/passenger-route/`
      );

      setPickupSpots(
        response.data.pickup_spots || []
      );

      const nextRoute =
        response.data.route || null;
      setRoadGeoJson(nextRoute);

      if (nextRoute) {
        setRouteVersion(
          (current) => current + 1
        );
      }

      rememberDriverLocation(
        response.data.driver_location
      );

      setRouteError("");
    } catch (requestError) {
      const responseStatus =
        requestError.response?.status;

      if ([403, 404].includes(responseStatus)) {
        onClose();
        return;
      }

      setRouteError(
        "Pickup route could not be refreshed. Retrying automatically."
      );
    } finally {
      routeInFlight.current = false;
    }
  },
  [dispatch.id, onClose, rememberDriverLocation]
);


  useEffect(() => {
    loadPickupRoute();

    const interval =
      window.setInterval(
        () => {
          loadPickupRoute(true);
        },
        15000
      );

    return () => {
      window.clearInterval(
        interval
      );
    };
  }, [loadPickupRoute]);


  useEffect(() => {
    loadDriverLocation();

    const interval =
      window.setInterval(
        () => {
          loadDriverLocation(true);
        },
        5000
      );

    return () => {
      window.clearInterval(
        interval
      );
    };
  }, [loadDriverLocation]);


  useEffect(() => {
    document.body.style.overflow =
      "hidden";

    return () => {
      document.body.style.overflow =
        "";
    };
  }, []);


  const passengerSpot =
    useMemo(
      () =>
        pickupSpots.find(
          (spot) =>
            spot.is_passenger_spot
        ) || null,
      [pickupSpots]
    );


  const passengerSpotPosition =
    useMemo(
      () =>
        passengerSpot
          ? [
              Number(
                passengerSpot.latitude
              ),
              Number(
                passengerSpot.longitude
              ),
            ]
          : null,
      [passengerSpot]
    );


  const driverPosition =
    useMemo(
      () =>
        driverLocation
          ? [
              Number(
                driverLocation.latitude
              ),
              Number(
                driverLocation.longitude
              ),
            ]
          : null,
      [driverLocation]
    );


  const pickupPositions =
    useMemo(
      () =>
        pickupSpots.map(
          (spot) => [
            Number(spot.latitude),
            Number(spot.longitude),
          ]
        ),
      [pickupSpots]
    );


  const stopsBeforeYou =
    useMemo(
      () =>
        pickupSpots.filter(
          (spot) =>
            !spot.is_passenger_spot
        ).length,
      [pickupSpots]
    );


  const remainingDistanceKm =
    useMemo(
      () => {
        const distanceMeters =
          roadGeoJson
            ?.features?.[0]
            ?.properties
            ?.summary
            ?.distance;

        if (
          distanceMeters === undefined
          || distanceMeters === null
        ) {
          return null;
        }

        return (
          Number(distanceMeters) / 1000
        ).toFixed(1);
      },
      [roadGeoJson]
    );


  const mapCenter =
    driverPosition
    || passengerSpotPosition
    || DEFAULT_MAP_CENTER;


  return (
    <div
      className="modal-backdrop"
      onMouseDown={onClose}
    >
      <section
        className={
          "dispatch-modal "
          + "waiting-spot-modal"
        }
        onMouseDown={(event) =>
          event.stopPropagation()
        }
      >
        <h3>
          Live Taxi Tracking
        </h3>


        {dispatch.driver && (
          <p>
            Driver:{" "}

            <strong>
              {dispatch.driver.name}
            </strong>

            {" · "}

            {
              dispatch.driver
                .number_plate
            }
          </p>
        )}


        {loading && (
          <p className="empty-note">
            Loading taxi location...
          </p>
        )}


        {!loading
          && !driverLocation
          && !error && (
          <p className="empty-note">
            Waiting for the Driver's
            first live location...
          </p>
        )}


        {error && (
          <div className="error-message">
            {error}
          </div>
        )}


        {driverLocation && passengerSpot && !routeError && (
          <div
            style={{
              display: "flex",
              justifyContent:
                "space-between",
              alignItems: "center",
              gap: "16px",
              padding: "12px 14px",
              marginBottom: "12px",
              borderRadius: "12px",
              background: "#f8fafc",
              border:
                "1px solid #e2e8f0",
            }}
          >
            <div>
              <strong>
                {stopsBeforeYou === 0
                  ? (
                    "Driver coming "
                    + "directly to you"
                  )
                  : (
                    `${stopsBeforeYou} pickup `
                    + `stop${
                      stopsBeforeYou === 1
                        ? ""
                        : "s"
                    } before you`
                  )}
              </strong>

              <div className="empty-note">
                Live route to{" "}

                {passengerSpot?.name
                  || "your pickup"}
              </div>
            </div>

            {remainingDistanceKm && (
              <strong>
                {remainingDistanceKm} km
              </strong>
            )}
          </div>
        )}


        <MapContainer
          center={mapCenter}
          zoom={
            driverPosition
            || passengerSpotPosition
              ? 16
              : 5
          }
          maxZoom={19}
          className="waiting-spot-map"
          scrollWheelZoom
        >
          <TileLayer
            attribution="&copy; OpenStreetMap contributors"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            maxZoom={19}
          />

          <TileLayer
            attribution="Labels &copy; Esri"
            url={
              "https://server.arcgisonline.com/"
              + "ArcGIS/rest/services/"
              + "Reference/"
              + "World_Boundaries_and_Places/"
              + "MapServer/tile/{z}/{y}/{x}"
            }
            maxZoom={19}
          />


          <TrackingViewport
            driverPosition={
              driverPosition
            }
            pickupPositions={
              pickupPositions
            }
          />


          {roadGeoJson && (
            <>
              <GeoJSON
                key={
                  `route-background-${routeVersion}`
                }
                data={roadGeoJson}
                style={() => ({
                  color: "#ffffff",
                  weight: 9,
                  opacity: 0.9,
                  lineCap: "round",
                  lineJoin: "round",
                })}
              />

              <GeoJSON
                key={
                  `route-main-${routeVersion}`
                }
                data={roadGeoJson}
                style={() => ({
                  color: "#16834a",
                  weight: 5,
                  opacity: 0.95,
                  lineCap: "round",
                  lineJoin: "round",
                })}
              />
            </>
          )}


          {pickupSpots.map(
            (spot) => (
              <CircleMarker
                key={spot.id}
                center={[
                  Number(
                    spot.latitude
                  ),
                  Number(
                    spot.longitude
                  ),
                ]}
                radius={
                  spot.is_passenger_spot
                    ? 10
                    : 7
                }
                pathOptions={
                  spot.is_passenger_spot
                    ? {
                        color:
                          "#ffffff",
                        fillColor:
                          "#16834a",
                        fillOpacity: 1,
                        weight: 3,
                      }
                    : {
                        color:
                          "#ffffff",
                        fillColor:
                          "#475569",
                        fillOpacity: 1,
                        weight: 3,
                      }
                }
              >
                <Tooltip
                  permanent
                  direction="top"
                  offset={[0, -10]}
                >
                  {spot.is_passenger_spot
                    ? (
                      `Your pickup · `
                      + `${spot.name}`
                    )
                    : (
                      `Pickup · `
                      + `${spot.name}`
                    )}
                </Tooltip>

                <Popup>
                  {spot.is_passenger_spot
                    ? (
                      `Your pickup: `
                      + `${spot.name}`
                    )
                    : (
                      `Passenger pickup: `
                      + `${spot.name}`
                    )}
                </Popup>
              </CircleMarker>
            )
          )}


          {driverPosition && (
            <Marker
              position={
                driverPosition
              }
              icon={TAXI_ICON}
            >
              <Tooltip
                permanent
                direction="top"
                offset={[0, -18]}
              >
                Driver
              </Tooltip>

              <Popup>
                Your assigned taxi
              </Popup>
            </Marker>
          )}
        </MapContainer>


        {driverLocation && (
          <p className="empty-note">
            Last location update:{" "}

            {new Date(
              driverLocation.updated_at
            ).toLocaleTimeString()}
          </p>
        )}


        <div className="dispatch-actions">
          <button
            className="secondary-button"
            type="button"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </section>
    </div>
  );
}
