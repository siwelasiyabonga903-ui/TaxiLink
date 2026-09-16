// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import {
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import api from "../api/client";
import RoutesPage from "./RoutesPage";


vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));


vi.mock(
  "../components/AppLayout",
  () => ({
    default: ({ children }) => (
      <div>{children}</div>
    ),
  })
);


vi.mock(
  "../context/AuthContext",
  () => ({
    useAuth: () => ({
      user: {
        role: "PASSENGER",
      },
    }),
  })
);


vi.mock("leaflet", () => ({
  divIcon: vi.fn(() => ({})),
}));


vi.mock(
  "react-leaflet",
  () => ({
    Circle: () => null,
    CircleMarker: ({ children }) => (
      <>{children}</>
    ),
    MapContainer: ({ children }) => (
      <div>{children}</div>
    ),
    Marker: ({ children }) => (
      <>{children}</>
    ),
    Popup: ({ children }) => (
      <>{children}</>
    ),
    TileLayer: () => null,
    useMap: () => ({
      setView: vi.fn(),
    }),
    useMapEvents: vi.fn(),
  })
);


const ROUTES = [
  {
    id: 1,
    name: "Campus to Town",
    origin: "University Campus",
    destination: "Town Taxi Rank",
    is_active: true,
    waiting_spots: [
      {
        id: 10,
        name: "Block A",
        latitude: "-23.875365",
        longitude: "29.735473",
        geofence_radius_meters: 100,
        is_active: true,
      },
    ],
  },
];


describe(
  "RoutesPage passenger check-in",
  () => {
    beforeEach(() => {
      vi.clearAllMocks();


      api.get.mockImplementation(
        (url) => {
          if (
            url
            === "/transport/routes/"
          ) {
            return Promise.resolve({
              data: ROUTES,
            });
          }

          if (
            url
            === (
              "/transport/"
              + "waiting-requests/current/"
            )
          ) {
            return Promise.resolve({
              data: {
                request: null,
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


      api.post.mockResolvedValue({
        data: {},
      });


      Object.defineProperty(
        navigator,
        "geolocation",
        {
          configurable: true,

          value: {
            getCurrentPosition:
              vi.fn((success) => {
                success({
                  coords: {
                    latitude:
                      -23.875365,

                    longitude:
                      29.735473,
                  },
                });
              }),
          },
        }
      );
    });


    it(
      "sends the selected party size when the passenger checks in",
      async () => {
        render(
          <RoutesPage />
        );


        expect(
          await screen.findByText(
            "Campus to Town"
          )
        ).toBeInTheDocument();


        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name:
                /waiting spots/i,
            }
          )
        );


        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name:
                "I'm Waiting",
            }
          )
        );


        expect(
          screen.getByText(
            "Confirm Waiting"
          )
        ).toBeInTheDocument();


        const partySizeSelect =
          screen.getByLabelText(
            "Number of passengers"
          );


        fireEvent.change(
          partySizeSelect,
          {
            target: {
              value: "4",
            },
          }
        );


        expect(
          partySizeSelect
        ).toHaveValue("4");


        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name:
                "Confirm Waiting",
            }
          )
        );


        await waitFor(() => {
          expect(
            api.post
          ).toHaveBeenCalledWith(
            "/transport/waiting-requests/check-in/",
            {
              waiting_spot: 10,
              party_size: 4,
              latitude:
                "-23.875365",
              longitude:
                "29.735473",
            }
          );
        });
      }
    );
  }
);