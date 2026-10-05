// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
} from "@testing-library/react";


import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import api from "../api/client";
import PassengerTaxiTrackingModal
  from "./PassengerTaxiTrackingModal";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
  },
}));

vi.mock("leaflet", () => ({
  divIcon: vi.fn(() => ({})),
}));

vi.mock(
  "react-leaflet",
  () => ({
    CircleMarker: ({ children }) => (
      <>{children}</>
    ),

    GeoJSON: () => (
      <span data-testid="tracking-road-route" />
    ),

    MapContainer: ({ children }) => (
      <div data-testid="tracking-map">
        {children}
      </div>
    ),

    Marker: ({ position, children }) => (
      <div
        data-testid="taxi-marker"
        data-position={position.join(",")}
      >
        {children}
      </div>
    ),

    Popup: ({ children }) => (
      <>{children}</>
    ),

    Tooltip: ({ children }) => (
      <>{children}</>
    ),

    TileLayer: () => null,

    useMap: () => ({
      fitBounds: vi.fn(),
      setView: vi.fn(),
    }),
  })
);

const DISPATCH = {
  id: 7,
  route_id: 3,
  status: "EN_ROUTE",
  driver: {
    name: "Thabo Mokoena",
    number_plate: "ABC 123 L",
  },
};

const WAITING_REQUEST = {
  waiting_spot: 10,
};

describe(
  "PassengerTaxiTrackingModal",
  () => {
    afterEach(() => {
      cleanup();
      vi.useRealTimers();
      vi.restoreAllMocks();
    });



    beforeEach(() => {
      vi.clearAllMocks();

      api.get.mockImplementation(
        (url) => {
          if (
            url
            === "/transport/dispatches/7/passenger-route/"
          ) {
            return Promise.resolve({
              data: {
                available: true,
                dispatch: 7,
                driver_location: {
                  latitude: -23.885,
                  longitude: 29.739,
                  accuracy_meters: 8.5,
                  updated_at:
                    "2026-09-19T10:00:00Z",
                },
                pickup_spots: [
                  {
                    id: 10,
                    name: "Main Gate",
                    stop_order: 3,
                    latitude: -23.8845,
                    longitude: 29.7382,
                    is_passenger_spot: true,
                  },
                ],
                route: {
                  type: "FeatureCollection",
                  features: [],
                },
              },
            });
          }

          if (
            url
            === "/transport/dispatches/7/location/"
          ) {
            return Promise.resolve({
              data: {
                available: true,
                dispatch: 7,
                latitude: -23.885,
                longitude: 29.739,
                accuracy_meters: 8.5,
                updated_at:
                  "2026-09-19T10:00:00Z",
              },
            });
          }

          return Promise.reject(
            new Error("Unexpected GET request")
          );
        }
      );
    });

    it(
      "loads and displays the live taxi",
      async () => {
        render(
          <PassengerTaxiTrackingModal
            dispatch={DISPATCH}
            waitingRequest={WAITING_REQUEST}
            onClose={vi.fn()}
          />
        );

        expect(
          screen.getByText(
            "Live Taxi Tracking"
          )
        ).toBeInTheDocument();

        await waitFor(() => {
          expect(
            screen.getByTestId(
              "tracking-map"
            )
          ).toHaveTextContent(
            "Your assigned taxi"
          );
        });

        expect(
          api.get
        ).toHaveBeenCalledWith(
          "/transport/dispatches/7/location/"
        );

        expect(
          api.get
        ).toHaveBeenCalledWith(
          "/transport/dispatches/7/passenger-route/"
        );
      }
    );

    it(
      "shows a waiting message before the driver has sent a location",
      async () => {
        api.get.mockImplementation(
          (url) => {
            if (
              url
              === "/transport/dispatches/7/location/"
            ) {
              return Promise.resolve({
                data: {
                  available: false,
                  dispatch: 7,
                  location: null,
                },
              });
            }

            if (
              url
              === "/transport/dispatches/7/passenger-route/"
            ) {
              return Promise.resolve({
                data: {
                  available: false,
                  dispatch: 7,
                  driver_location: null,
                  pickup_spots: [
                    {
                      id: 10,
                      name: "Main Gate",
                      stop_order: 3,
                      latitude: -23.8845,
                      longitude: 29.7382,
                      is_passenger_spot: true,
                    },
                  ],
                  route: null,
                },
              });
            }

            return Promise.reject(
              new Error(
                "Unexpected GET request"
              )
            );
          }
        );

        render(
          <PassengerTaxiTrackingModal
            dispatch={DISPATCH}
            waitingRequest={WAITING_REQUEST}
            onClose={vi.fn()}
          />
        );

        expect(
          await screen.findByText(
            /Waiting for the Driver's first live location/i
          )
        ).toBeInTheDocument();
      }
    );

    const locationUrl =
  "/transport/dispatches/7/location/";
const routeUrl =
  "/transport/dispatches/7/passenger-route/";

async function showTracking(onClose) {
  await act(async () => {
    render(
      <PassengerTaxiTrackingModal
        dispatch={DISPATCH}
        waitingRequest={WAITING_REQUEST}
        onClose={onClose}
      />
    );
  });
}

it(
  "keeps GPS polling when the route initially fails, then recovers",
  async () => {
    vi.useFakeTimers();

    const normalGet = api.get.getMockImplementation();
    let routeUnavailable = true;

    api.get.mockImplementation((url) => {
      if (url === routeUrl && routeUnavailable) {
        return Promise.reject({
          response: { status: 400 },
        });
      }

      return normalGet(url);
    });

    const onClose = vi.fn();
    await showTracking(onClose);

    expect(
      screen.getByText(
        /Pickup route could not be refreshed/i
      )
    ).toBeInTheDocument();

    expect(
      screen.getByTestId("tracking-map")
    ).toHaveTextContent("Your assigned taxi");

    const locationCalls = api.get.mock.calls.filter(
      ([url]) => url === locationUrl
    ).length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(
      api.get.mock.calls.filter(
        ([url]) => url === locationUrl
      ).length
    ).toBeGreaterThan(locationCalls);

    expect(
      screen.getByText(
        /Pickup route could not be refreshed/i
      )
    ).toBeInTheDocument();

    routeUnavailable = false;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });

    expect(
      screen.queryByText(
        /Pickup route could not be refreshed/i
      )
    ).not.toBeInTheDocument();

    expect(
      screen.getByText(/Driver coming directly to you/i)
    ).toBeInTheDocument();

    expect(onClose).not.toHaveBeenCalled();
  }
);

it(
  "preserves the last road route during an outage",
  async () => {
    vi.useFakeTimers();

    const normalGet = api.get.getMockImplementation();
    let routeUnavailable = false;

    api.get.mockImplementation((url) => {
      if (url === routeUrl && routeUnavailable) {
        return Promise.reject({
          response: { status: 400 },
        });
      }

      return normalGet(url);
    });

    const onClose = vi.fn();
    await showTracking(onClose);

    expect(
      screen.getAllByTestId("tracking-road-route")
    ).toHaveLength(2);

    routeUnavailable = true;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });

    expect(
      screen.getByText(
        /Pickup route could not be refreshed/i
      )
    ).toBeInTheDocument();

    expect(
      screen.getAllByTestId("tracking-road-route")
    ).toHaveLength(2);

    expect(
      screen.getByTestId("tracking-map")
    ).toHaveTextContent("Your assigned taxi");

    routeUnavailable = false;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });

    expect(
      screen.queryByText(
        /Pickup route could not be refreshed/i
      )
    ).not.toBeInTheDocument();

    expect(onClose).not.toHaveBeenCalled();
  }
);

it(
  "keeps a GPS warning until GPS itself recovers",
  async () => {
    vi.useFakeTimers();

    const normalGet = api.get.getMockImplementation();
    let gpsUnavailable = false;

    api.get.mockImplementation((url) => {
      if (url === locationUrl && gpsUnavailable) {
        return Promise.reject(
          new Error("Temporary GPS failure")
        );
      }

      return normalGet(url);
    });

    const onClose = vi.fn();
    await showTracking(onClose);

    gpsUnavailable = true;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(
      screen.getByText(
        /Taxi location could not be refreshed/i
      )
    ).toBeInTheDocument();

    expect(
      screen.getByTestId("tracking-map")
    ).toHaveTextContent("Your assigned taxi");

    // A successful route refresh must not clear the GPS warning.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });

    expect(
      screen.getByText(
        /Taxi location could not be refreshed/i
      )
    ).toBeInTheDocument();

    gpsUnavailable = false;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(
      screen.queryByText(
        /Taxi location could not be refreshed/i
      )
    ).not.toBeInTheDocument();

    expect(onClose).not.toHaveBeenCalled();
  }
);

it.each([
  [locationUrl, 400],
  [locationUrl, 403],
  [locationUrl, 404],
  [routeUrl, 403],
  [routeUrl, 404],
])(
  "closes tracking when %s returns %i",
  async (failingUrl, responseStatus) => {
    const normalGet = api.get.getMockImplementation();

    api.get.mockImplementation((url) => {
      if (url === failingUrl) {
        return Promise.reject({
          response: { status: responseStatus },
        });
      }

      return normalGet(url);
    });

    const onClose = vi.fn();
    await showTracking(onClose);

    await waitFor(() => {
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  }
);

          it(
  "does not let an older route response rewind the taxi position",
  async () => {
    const normalGet = api.get.getMockImplementation();
    let resolveRoute;

    api.get.mockImplementation((url) => {
      if (url === routeUrl) {
        return new Promise((resolve) => {
          resolveRoute = resolve;
        });
      }

      if (url === locationUrl) {
        return Promise.resolve({
          data: {
            available: true,
            dispatch: 7,
            latitude: -23.88,
            longitude: 29.74,
            updated_at: "2026-09-19T10:00:10Z",
          },
        });
      }

      return normalGet(url);
    });

    await showTracking(vi.fn());

    expect(
      screen.getByTestId("taxi-marker")
    ).toHaveAttribute(
      "data-position",
      "-23.88,29.74"
    );

    const olderRoute = await normalGet(routeUrl);
    olderRoute.data.driver_location.updated_at =
      "2026-09-19T10:00:00Z";

    await act(async () => {
      resolveRoute(olderRoute);
    });

    expect(
      screen.getByTestId("taxi-marker")
    ).toHaveAttribute(
      "data-position",
      "-23.88,29.74"
    );
  }
);

it(
  "does not overlap GPS polls while a request is pending",
  async () => {
    vi.useFakeTimers();

    const normalGet = api.get.getMockImplementation();
    let locationCalls = 0;

    api.get.mockImplementation((url) => {
      if (url === locationUrl) {
        locationCalls += 1;

        if (locationCalls === 2) {
          return new Promise(() => {});
        }
      }

      return normalGet(url);
    });

    await showTracking(vi.fn());
    expect(locationCalls).toBe(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(locationCalls).toBe(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(locationCalls).toBe(2);
  }
);
  }
);
