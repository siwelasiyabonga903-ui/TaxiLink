import {
  useCallback,
  useEffect,
  useState,
} from "react";

import { divIcon } from "leaflet";

import {
  Circle,
  CircleMarker,
  GeoJSON,
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";
import { createPortal } from "react-dom";

import api from "../api/client";
import AppLayout from "../components/AppLayout";
import { useAuth } from "../context/AuthContext";


const DEFAULT_MAP_CENTER = [
  -30.5595,
  22.9375,
];


const CURRENT_LOCATION_ICON = divIcon({
  className: "",

  html: `
    <svg
      width="32"
      height="40"
      viewBox="0 0 32 40"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="
          M16 1
          C7.7 1 1 7.7 1 16
          C1 27 16 39 16 39
          C16 39 31 27 31 16
          C31 7.7 24.3 1 16 1
          Z
        "
        fill="#dc2626"
        stroke="#ffffff"
        stroke-width="2"
      />

      <circle
        cx="16"
        cy="16"
        r="6"
        fill="#ffffff"
      />
    </svg>
  `,

  iconSize: [32, 40],
  iconAnchor: [16, 40],
  popupAnchor: [0, -38],
});


const initialRouteForm = {
  name: "",
  origin: "",
  destination: "",
};


const initialSpotForm = {
  route: "",
  name: "",
  latitude: "",
  longitude: "",
  geofence_radius_meters: 100,
};


function getRouteWaitingCount(route) {
  return (
    route.waiting_spots || []
  ).reduce(
    (total, spot) =>
      total
      + Number(
        spot.active_waiting_count || 0
      ),
    0
  );
}


function getBrowserLocation() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(
        new Error(
          "Location services are not supported by this browser."
        )
      );

      return;
    }

    navigator.geolocation.getCurrentPosition(
      resolve,
      reject,
      {
        enableHighAccuracy: true,
        timeout: 15000,
        maximumAge: 0,
      }
    );
  });
}


function extractError(
  error,
  fallbackMessage
) {
  const data = error.response?.data;

  if (!data) {
    return (
      error.message
      || fallbackMessage
    );
  }

  const firstValue =
    Object.values(data).flat()[0];

  return String(
    firstValue
    || fallbackMessage
  );
}


function MapClickHandler({
  onLocationSelect,
}) {
  useMapEvents({
    click(event) {
      onLocationSelect(
        event.latlng.lat,
        event.latlng.lng
      );
    },
  });

  return null;
}


function RecenterMap({
  center,
  zoom,
}) {
  const map = useMap();

  useEffect(() => {
    map.setView(
      center,
      zoom
    );
  }, [
    map,
    center,
    zoom,
  ]);

  return null;
}


export default function RoutesPage() {
  const { user } = useAuth();

  const [routes, setRoutes] =
    useState([]);

  const [
    currentWaiting,
    setCurrentWaiting,
  ] = useState(null);

  const [
    selectedSpotForCheckIn,
    setSelectedSpotForCheckIn,
  ] = useState(null);

  const [
    partySize,
    setPartySize,
  ] = useState(1);


  const [routeForm, setRouteForm] =
    useState(initialRouteForm);

  const [spotForm, setSpotForm] =
    useState(initialSpotForm);


  const [
    createRouteOpen,
    setCreateRouteOpen,
  ] = useState(false);

  const [
    selectedRouteForSpot,
    setSelectedRouteForSpot,
  ] = useState(null);


  const [
    expandedRoutes,
    setExpandedRoutes,
  ] = useState({});


  const [mapCenter, setMapCenter] =
    useState(DEFAULT_MAP_CENTER);

  const [mapZoom, setMapZoom] =
    useState(5);

  const [
    dispatcherLocation,
    setDispatcherLocation,
  ] = useState(null);

  const [
  routeRoadGeoJson,
  setRouteRoadGeoJson,
  ] = useState(null);

  const [loading, setLoading] =
    useState(true);

  const [
    checkingSpotId,
    setCheckingSpotId,
  ] = useState(null);

  const [
    locatingDispatcher,
    setLocatingDispatcher,
  ] = useState(false);


  const [error, setError] =
    useState("");

  const [message, setMessage] =
    useState("");


  const isPassenger =
    user.role === "PASSENGER";

  const isDispatcher =
    user.role === "DISPATCHER";


  const loadData = useCallback(
    async (silent = false) => {
      if (!silent) {
        setLoading(true);
      }

      try {
        const routesResponse =
          await api.get(
            "/transport/routes/"
          );

        setRoutes(
          routesResponse.data
        );


        if (isPassenger) {
          const waitingResponse =
            await api.get(
              "/transport/waiting-requests/current/"
            );

          setCurrentWaiting(
            waitingResponse.data.request
          );
        } else {
          setCurrentWaiting(null);
        }
      } catch {
        if (!silent) {
          setError(
            "TaxiLink data could not be loaded."
          );
        }
      } finally {
        if (!silent) {
          setLoading(false);
        }
      }
    },
    [isPassenger]
  );


  useEffect(() => {
    loadData();

    const refreshInterval =
      window.setInterval(
        () => {
          loadData(true);
        },
        10000
      );

    return () => {
      window.clearInterval(
        refreshInterval
      );
    };
  }, [loadData]);


  useEffect(() => {
    const modalOpen =
      createRouteOpen
      || Boolean(
        selectedRouteForSpot
      )
      || Boolean(
        selectedSpotForCheckIn
      );

    if (modalOpen) {
      document.body.style.overflow =
        "hidden";
    } else {
      document.body.style.overflow =
        "";
    }

    return () => {
      document.body.style.overflow =
        "";
    };
  }, [
    createRouteOpen,
    selectedRouteForSpot,
    selectedSpotForCheckIn,
  ]);


  const toggleRouteSpots = (
    routeId
  ) => {
    setExpandedRoutes(
      (current) => ({
        ...current,

        [routeId]:
          !current[routeId],
      })
    );
  };


  const handleRouteChange = (
    event
  ) => {
    setRouteForm({
      ...routeForm,
      [event.target.name]:
        event.target.value,
    });
  };


  const handleSpotChange = (
    event
  ) => {
    setSpotForm({
      ...spotForm,
      [event.target.name]:
        event.target.value,
    });
  };


  const openCreateRoute = () => {
    setError("");
    setMessage("");

    setRouteForm(
      initialRouteForm
    );

    setCreateRouteOpen(true);
  };


  const closeCreateRoute = () => {
    setCreateRouteOpen(false);

    setRouteForm(
      initialRouteForm
    );
  };


  const createRoute = async (
    event
  ) => {
    event.preventDefault();

    setError("");
    setMessage("");

    try {
      await api.post(
        "/transport/routes/",
        routeForm
      );

      setRouteForm(
        initialRouteForm
      );

      setCreateRouteOpen(false);

      setMessage(
        "Route created successfully."
      );

      await loadData(true);
    } catch (requestError) {
      setError(
        extractError(
          requestError,
          "Route could not be created."
        )
      );
    }
  };


  const openWaitingSpot = async (
    route
  ) => {
    setError("");
    setMessage("");

    setDispatcherLocation(null);

    setSelectedRouteForSpot(
      route
    );

    loadRoadRoute(route);

    setSpotForm({
      ...initialSpotForm,
      route: route.id,
    });

    setLocatingDispatcher(true);

    try {
      const position =
        await getBrowserLocation();

      const latitude =
        position.coords.latitude;

      const longitude =
        position.coords.longitude;

      const currentLocation = [
        latitude,
        longitude,
      ];

      setDispatcherLocation(
        currentLocation
      );

      setMapCenter(
        currentLocation
      );

      setMapZoom(17);
    } catch {
      const firstSpot =
        route.waiting_spots?.[0];

      if (firstSpot) {
        setMapCenter([
          Number(
            firstSpot.latitude
          ),
          Number(
            firstSpot.longitude
          ),
        ]);

        setMapZoom(16);
      } else {
        setMapCenter(
          DEFAULT_MAP_CENTER
        );

        setMapZoom(5);
      }
    } finally {
      setLocatingDispatcher(false);
    }
  };

  const loadRoadRoute = async (
  route
) => {
  setRouteRoadGeoJson(null);

  const activeSpots = (
    route.waiting_spots || []
  ).filter(
    (spot) => spot.is_active
  );

  if (activeSpots.length < 2) {
    return;
  }

  try {
    const response = await api.get(
      `/transport/routes/${route.id}/road-route/`
    );

    setRouteRoadGeoJson(
      response.data
    );
  } catch (requestError) {
    console.error(
      "Road route could not be loaded:",
      requestError
    );

    setRouteRoadGeoJson(null);
  }
};

  const closeWaitingSpot = () => {
    if (locatingDispatcher) {
      return;
    }

    setSelectedRouteForSpot(
      null
    );

    setRouteRoadGeoJson(
      null
    );

    setDispatcherLocation(
      null
    );

    setSpotForm(
      initialSpotForm
    );

    setMapCenter(
      DEFAULT_MAP_CENTER
    );

    setMapZoom(5);
  };


  const selectMapLocation = (
    latitude,
    longitude
  ) => {
    setSpotForm(
      (currentForm) => ({
        ...currentForm,

        latitude:
          latitude.toFixed(6),

        longitude:
          longitude.toFixed(6),
      })
    );

    setMapCenter([
      latitude,
      longitude,
    ]);

    setMapZoom(17);
  };


  const useCurrentLocationForSpot =
    async () => {
      setError("");
      setMessage("");

      setLocatingDispatcher(true);

      try {
        const position =
          await getBrowserLocation();

        const latitude =
          position.coords.latitude;

        const longitude =
          position.coords.longitude;

        setDispatcherLocation([
          latitude,
          longitude,
        ]);

        setSpotForm(
          (currentForm) => ({
            ...currentForm,

            latitude:
              latitude.toFixed(6),

            longitude:
              longitude.toFixed(6),
          })
        );

        setMapCenter([
          latitude,
          longitude,
        ]);

        setMapZoom(17);
      } catch (locationError) {
        setError(
          locationError.message
          || (
            "Your current location "
            + "could not be obtained."
          )
        );
      } finally {
        setLocatingDispatcher(false);
      }
    };


  const createWaitingSpot =
    async (event) => {
      event.preventDefault();

      setError("");
      setMessage("");

      if (
        !spotForm.latitude
        || !spotForm.longitude
      ) {
        setError(
          "Select the waiting spot location on the map."
        );

        return;
      }

      try {
        await api.post(
          "/transport/waiting-spots/",
          spotForm
        );

        setSpotForm(
          initialSpotForm
        );

        setDispatcherLocation(
          null
        );

        setSelectedRouteForSpot(
          null
        );

        setMessage(
          "Waiting spot created successfully."
        );

        await loadData(true);
      } catch (requestError) {
        setError(
          extractError(
            requestError,
            "Waiting spot could not be created."
          )
        );
      }
    };


  const toggleRoute = async (
    route
  ) => {
    setError("");
    setMessage("");

    try {
      await api.patch(
        `/transport/routes/${route.id}/`,
        {
          is_active:
            !route.is_active,
        }
      );

      await loadData(true);
    } catch {
      setError(
        "The route status could not be changed."
      );
    }
  };


  const toggleWaitingSpot =
    async (spot) => {
      setError("");
      setMessage("");

      try {
        await api.patch(
          `/transport/waiting-spots/${spot.id}/`,
          {
            is_active:
              !spot.is_active,
          }
        );

        await loadData(true);
      } catch {
        setError(
          "The waiting spot status could not be changed."
        );
      }
    };


  const openPassengerCheckIn = (
    spot
  ) => {
    if (currentWaiting) {
      return;
    }

    setError("");
    setMessage("");

    setSelectedSpotForCheckIn(
      spot
    );

    setPartySize(1);
  };


  const closePassengerCheckIn = () => {
    if (checkingSpotId) {
      return;
    }

    setSelectedSpotForCheckIn(
      null
    );

    setPartySize(1);
  };


  const checkInAtSpot = async (
    event
  ) => {
    event.preventDefault();

    if (!selectedSpotForCheckIn) {
      return;
    }

    const selectedPartySize =
      Number(partySize);

    if (
      !Number.isInteger(
        selectedPartySize
      )
      || selectedPartySize < 1
      || selectedPartySize > 15
    ) {
      setError(
        "Party size must be between 1 and 15."
      );

      return;
    }

    const spot =
      selectedSpotForCheckIn;

    setError("");
    setMessage("");

    setCheckingSpotId(
      spot.id
    );

    try {
      const position =
        await getBrowserLocation();

      await api.post(
        "/transport/waiting-requests/check-in/",
        {
          waiting_spot:
            spot.id,

          party_size:
            selectedPartySize,

          latitude:
            position.coords.latitude
              .toFixed(6),

          longitude:
            position.coords.longitude
              .toFixed(6),
        }
      );

      setSelectedSpotForCheckIn(
        null
      );

      setPartySize(1);

      setMessage(
        `You are now waiting at ${spot.name}.`
      );

      await loadData(true);
    } catch (requestError) {
      setError(
        extractError(
          requestError,
          "Your waiting request could not be created."
        )
      );
    } finally {
      setCheckingSpotId(null);
    }
  };


  const cancelWaitingRequest =
    async () => {
      setError("");
      setMessage("");

      try {
        await api.post(
          "/transport/waiting-requests/cancel/"
        );

        setCurrentWaiting(null);

        setMessage(
          "Your waiting request was cancelled."
        );

        await loadData(true);
      } catch (requestError) {
        setError(
          extractError(
            requestError,
            "The waiting request could not be cancelled."
          )
        );
      }
    };


  const selectedPosition =
    spotForm.latitude
    && spotForm.longitude
      ? [
          Number(
            spotForm.latitude
          ),
          Number(
            spotForm.longitude
          ),
        ]
      : null;

  const modalIsOpen = Boolean(
    createRouteOpen
    || selectedRouteForSpot
    || selectedSpotForCheckIn
  );
  return (
    <AppLayout>
      <section className="page-heading">
        <h2>
          Routes and Waiting Spots
        </h2>

        <p>
          Route information refreshes
          automatically every 10 seconds.
        </p>
      </section>


      {message && (
        <div className="success-message">
          {message}
        </div>
      )}


      {error && (
        modalIsOpen ? createPortal(
          <div
            className="error-message"
            role="alert"
            style={{
              position: "fixed",
              top: 16,
              left: "50%",
              transform: "translateX(-50%)",
              width: "min(600px, calc(100vw - 32px))",
              maxHeight: "40vh",
              overflowY: "auto",
              boxSizing: "border-box",
              zIndex: 2147483647,
            }}
          >
            {error}
          </div>,
          document.body
        ) : (
          <div className="error-message" role="alert">
            {error}
          </div>
        )
      )}


      {isPassenger
        && currentWaiting && (
        <section className="current-waiting-card">
          <div>
            <span className="status-badge active">
              Currently waiting
            </span>

            <h3>
              {
                currentWaiting
                  .waiting_spot_name
              }
            </h3>

            <p>
              Route:{" "}
              {
                currentWaiting
                  .route_name
              }
            </p>

            
          </div>

          <button
            className="danger-button"
            type="button"
            onClick={
              cancelWaitingRequest
            }
          >
            Cancel waiting request
          </button>
        </section>
      )}


      {isDispatcher && (
        <div className="route-page-actions">
          <button
            className="action-button"
            type="button"
            onClick={
              openCreateRoute
            }
          >
            + Create Route
          </button>
        </div>
      )}


      {loading ? (
        <div className="page-message">
          Loading routes...
        </div>
      ) : (
        <section className="list-stack">
          {routes.length === 0 && (
            <div className="route-card">
              No active routes are
              available.
            </div>
          )}


          {routes.map((route) => {
            const routeWaitingCount =
              getRouteWaitingCount(
                route
              );

            const spotsExpanded =
              Boolean(
                expandedRoutes[
                  route.id
                ]
              );

            return (
              <article
                className="route-card"
                key={route.id}
              >
                <div className="route-header">
                  <div>
                    <h3>
                      {route.name}
                    </h3>

                    <p>
                      {route.origin}
                      {" → "}
                      {
                        route.destination
                      }
                    </p>


                    {isDispatcher && (
                      <span className="waiting-count">
                        {routeWaitingCount}
                        {" "}

                        {routeWaitingCount === 1
                          ? "person waiting"
                          : "people waiting"}

                        {" "}on this route
                      </span>
                    )}
                  </div>


                  <div className="spot-actions">
                    <span
                      className={
                        route.is_active
                          ? "status-badge active"
                          : "status-badge inactive"
                      }
                    >
                      {route.is_active
                        ? "Active"
                        : "Inactive"}
                    </span>


                    {isDispatcher && (
                      <>
                        <button
                          className="action-button"
                          type="button"
                          onClick={() =>
                            openWaitingSpot(
                              route
                            )
                          }
                        >
                          + Add Waiting Spot
                        </button>

                        <button
                          className="secondary-button"
                          type="button"
                          onClick={() =>
                            toggleRoute(
                              route
                            )
                          }
                        >
                          {route.is_active
                            ? "Deactivate"
                            : "Activate"}
                        </button>
                      </>
                    )}
                  </div>
                </div>


                <button
                  className="route-spots-toggle"
                  type="button"
                  aria-expanded={
                    spotsExpanded
                  }
                  onClick={() =>
                    toggleRouteSpots(
                      route.id
                    )
                  }
                >
                  <span>
                    Waiting Spots
                  </span>

                  <span className="route-spots-toggle-info">
                    {
                      route
                        .waiting_spots
                        .length
                    }
                    {" "}

                    {route
                      .waiting_spots
                      .length === 1
                      ? "spot"
                      : "spots"}

                    <strong>
                      {spotsExpanded
                        ? "▲"
                        : "▼"}
                    </strong>
                  </span>
                </button>


                {spotsExpanded && (
                  <div className="spot-list">
                    {route.waiting_spots
                      .length === 0 && (
                      <p>
                        No waiting spots
                        for this route.
                      </p>
                    )}


                    {route.waiting_spots.map(
                      (spot) => {
                        const waitingHere =
                          currentWaiting
                            ?.waiting_spot
                          === spot.id;

                        return (
                          <div
                            className="spot-item"
                            key={spot.id}
                          >
                            <div>
                              <strong>
                                {spot.name}
                              </strong>

                              <small>
                                Geofence radius:{" "}
                                {
                                  spot
                                    .geofence_radius_meters
                                }{" "}
                                metres
                              </small>
                            </div>


                            <div className="spot-actions">
                              {isDispatcher && (
                                <span className="waiting-count">
                                  {
                                    spot
                                      .active_waiting_count
                                  }{" "}
                                  waiting
                                </span>
                              )}


                              <span
                                className={
                                  spot.is_active
                                    ? "status-badge active"
                                    : "status-badge inactive"
                                }
                              >
                                {spot.is_active
                                  ? "Active"
                                  : "Inactive"}
                              </span>


                              {isPassenger && (
                                <button
                                  className="action-button"
                                  type="button"
                                  disabled={
                                    Boolean(
                                      currentWaiting
                                    )
                                    || checkingSpotId
                                      === spot.id
                                  }
                                  onClick={() =>
                                    openPassengerCheckIn(
                                      spot
                                    )
                                  }
                                >
                                  {waitingHere
                                    ? "Waiting here"
                                    : checkingSpotId
                                        === spot.id
                                      ? "Checking location..."
                                      : currentWaiting
                                        ? "Already checked in"
                                        : "I'm Waiting"}
                                </button>
                              )}


                              {isDispatcher && (
                                <button
                                  className="secondary-button"
                                  type="button"
                                  onClick={() =>
                                    toggleWaitingSpot(
                                      spot
                                    )
                                  }
                                >
                                  {spot.is_active
                                    ? "Deactivate"
                                    : "Activate"}
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      }
                    )}
                  </div>
                )}
              </article>
            );
          })}
        </section>
      )}


      {isPassenger
        && selectedSpotForCheckIn && (
        <div
          className="modal-backdrop"
          onMouseDown={
            closePassengerCheckIn
          }
        >
          <section
            className="dispatch-modal"
            onMouseDown={(event) =>
              event.stopPropagation()
            }
          >
            <h3>
              Confirm Waiting Request
            </h3>

            <p>
              Waiting spot:{" "}

              <strong>
                {
                  selectedSpotForCheckIn
                    .name
                }
              </strong>
            </p>


            <form
              onSubmit={
                checkInAtSpot
              }
            >
              <label>
                Number of passengers

                <select
                  value={partySize}
                  onChange={(event) =>
                    setPartySize(
                      event.target.value
                    )
                  }
                  required
                >
                  {Array.from(
                    { length: 15 },
                    (_, index) =>
                      index + 1
                  ).map((number) => (
                    <option
                      key={number}
                      value={number}
                    >
                      {number}
                    </option>
                  ))}
                </select>
              </label>


              <p className="empty-note">
                Maximum 15 passengers.
              </p>


              <div className="dispatch-actions">
                <button
                  className="secondary-button"
                  type="button"
                  disabled={
                    Boolean(
                      checkingSpotId
                    )
                  }
                  onClick={
                    closePassengerCheckIn
                  }
                >
                  Cancel
                </button>

                <button
                  className="action-button"
                  type="submit"
                  disabled={
                    Boolean(
                      checkingSpotId
                    )
                  }
                >
                  {checkingSpotId
                    ? "Checking location..."
                    : "Confirm Waiting"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}


      {createRouteOpen && (
        <div
          className="modal-backdrop"
          onMouseDown={
            closeCreateRoute
          }
        >
          <section
            className="dispatch-modal"
            onMouseDown={(event) =>
              event.stopPropagation()
            }
          >
            <h3>
              Create Route
            </h3>

            <form
              onSubmit={
                createRoute
              }
            >
              <label>
                Route name

                <input
                  name="name"
                  placeholder={
                    "e.g. Campus to Town"
                  }
                  value={
                    routeForm.name
                  }
                  onChange={
                    handleRouteChange
                  }
                  required
                />
              </label>


              <label>
                Origin

                <input
                  name="origin"
                  placeholder={
                    "e.g. University Campus"
                  }
                  value={
                    routeForm.origin
                  }
                  onChange={
                    handleRouteChange
                  }
                  required
                />
              </label>


              <label>
                Destination

                <input
                  name="destination"
                  placeholder={
                    "e.g. Town Taxi Rank"
                  }
                  value={
                    routeForm.destination
                  }
                  onChange={
                    handleRouteChange
                  }
                  required
                />
              </label>


              <div className="dispatch-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={
                    closeCreateRoute
                  }
                >
                  Cancel
                </button>

                <button
                  className="action-button"
                  type="submit"
                >
                  Create Route
                </button>
              </div>
            </form>
          </section>
        </div>
      )}


      {selectedRouteForSpot && (
        <div
          className="modal-backdrop"
          onMouseDown={
            closeWaitingSpot
          }
        >
          <section
            className="dispatch-modal waiting-spot-modal"
            onMouseDown={(event) =>
              event.stopPropagation()
            }
          >
            <h3>
              Add Waiting Spot
            </h3>

            <p>
              Route:{" "}

              <strong>
                {
                  selectedRouteForSpot
                    .name
                }
              </strong>
            </p>


            <form
              onSubmit={
                createWaitingSpot
              }
            >
              <label>
                Waiting spot name

                <input
                  name="name"
                  placeholder={
                    "e.g. Block A"
                  }
                  value={
                    spotForm.name
                  }
                  onChange={
                    handleSpotChange
                  }
                  required
                />
              </label>


              <button
                className="secondary-button"
                type="button"
                disabled={
                  locatingDispatcher
                }
                onClick={
                  useCurrentLocationForSpot
                }
              >
                {locatingDispatcher
                  ? "Getting location..."
                  : "Use My Current Location"}
              </button>


              <div>
                <strong>
                  Select location
                </strong>

                <p className="empty-note">
                  Click the satellite map
                  to place the waiting spot.
                </p>
              </div>


              <MapContainer
                center={
                  mapCenter
                }
                zoom={
                  mapZoom
                }
                maxZoom={18}
                className="waiting-spot-map"
                scrollWheelZoom
              >
                <TileLayer
                  attribution={
                    "Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"
                  }
                  url={
                    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                  }
                  maxNativeZoom={18}
                  maxZoom={18}
                />


                <RecenterMap
                  center={
                    mapCenter
                  }
                  zoom={
                    mapZoom
                  }
                />


                <MapClickHandler
                  onLocationSelect={
                    selectMapLocation
                  }
                />

                  {routeRoadGeoJson && (
                    <GeoJSON
                      key={
                        `road-route-${selectedRouteForSpot.id}`
                      }
                      data={
                        routeRoadGeoJson
                      }
                    />
                  )}

                {selectedRouteForSpot
                  .waiting_spots
                  ?.map(
                    (spot) => (
                      <CircleMarker
                        key={
                          spot.id
                        }
                        center={[
                          Number(
                            spot.latitude
                          ),
                          Number(
                            spot.longitude
                          ),
                        ]}
                        radius={5}
                      >
                        <Popup>
                          Existing spot:{" "}
                          {spot.name}
                        </Popup>
                      </CircleMarker>
                    )
                  )}


                {selectedPosition && (
                  <>
                    <CircleMarker
                      center={
                        selectedPosition
                      }
                      radius={8}
                    >
                      <Popup>
                        New waiting spot
                      </Popup>
                    </CircleMarker>

                    <Circle
                      center={
                        selectedPosition
                      }
                      radius={
                        Number(
                          spotForm
                            .geofence_radius_meters
                        ) || 100
                      }
                    />
                  </>
                )}


                {dispatcherLocation && (
                  <Marker
                    position={
                      dispatcherLocation
                    }
                    icon={
                      CURRENT_LOCATION_ICON
                    }
                  >
                    <Popup>
                      Your current location
                    </Popup>
                  </Marker>
                )}
              </MapContainer>


              {locatingDispatcher && (
                <p className="empty-note">
                  Finding your current
                  location...
                </p>
              )}


              {selectedPosition ? (
                <p className="selected-location">
                  Waiting spot location selected.
                </p>
              ) : (
                !locatingDispatcher && (
                  <p className="empty-note">
                    No waiting spot location
                    selected yet.
                  </p>
                )
              )}


              <label>
                Geofence radius
                (metres)

                <input
                  name="geofence_radius_meters"
                  type="number"
                  min="20"
                  max="1000"
                  value={
                    spotForm
                      .geofence_radius_meters
                  }
                  onChange={
                    handleSpotChange
                  }
                  required
                />
              </label>


              <div className="dispatch-actions">
                <button
                  className="secondary-button"
                  type="button"
                  disabled={
                    locatingDispatcher
                  }
                  onClick={
                    closeWaitingSpot
                  }
                >
                  Cancel
                </button>

                <button
                  className="action-button"
                  type="submit"
                  disabled={
                    !selectedPosition
                    || locatingDispatcher
                  }
                >
                  Add Waiting Spot
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </AppLayout>
  );
}