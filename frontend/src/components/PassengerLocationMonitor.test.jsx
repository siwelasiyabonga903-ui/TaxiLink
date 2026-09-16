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
import PassengerLocationMonitor
  from "./PassengerLocationMonitor";


vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));


const WAITING_REQUEST = {
  id: 1,
  status: "WAITING",
};


function setSuccessfulLocation() {
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
                latitude: -23.8845,
                longitude: 29.7382,
              },
            });
          }),
      },
    }
  );
}


async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}


describe(
  "PassengerLocationMonitor",
  () => {
    beforeEach(() => {
      vi.clearAllMocks();

      setSuccessfulLocation();
    });


    afterEach(() => {
      cleanup();

      vi.useRealTimers();
    });


    it(
      "does not request GPS when there is no active waiting request",
      async () => {
        api.get.mockResolvedValue({
          data: {
            request: null,
          },
        });

        render(
          <PassengerLocationMonitor />
        );

        await waitFor(() => {
          expect(
            api.get
          ).toHaveBeenCalledTimes(1);
        });

        expect(
          navigator.geolocation
            .getCurrentPosition
        ).not.toHaveBeenCalled();

        expect(
          api.post
        ).not.toHaveBeenCalled();
      }
    );


    it(
      "revalidates the passenger location when waiting",
      async () => {
        api.get.mockResolvedValue({
          data: {
            request: WAITING_REQUEST,
          },
        });

        api.post.mockResolvedValue({
          data: {
            active: true,
            cancelled: false,
            inside_geofence: true,
            grace_period_active: false,
          },
        });

        render(
          <PassengerLocationMonitor />
        );

        await waitFor(() => {
          expect(
            api.post
          ).toHaveBeenCalledWith(
            "/transport/waiting-requests/revalidate-location/",
            {
              latitude: "-23.884500",
              longitude: "29.738200",
            }
          );
        });

        expect(
          screen.queryByText(
            /outside the waiting spot/i
          )
        ).not.toBeInTheDocument();
      }
    );


    it(
      "shows a warning while the geofence grace period is active",
      async () => {
        api.get.mockResolvedValue({
          data: {
            request: WAITING_REQUEST,
          },
        });

        api.post.mockResolvedValue({
          data: {
            active: true,
            cancelled: false,
            inside_geofence: false,
            grace_period_active: true,
          },
        });

        render(
          <PassengerLocationMonitor />
        );

        expect(
          await screen.findByText(
            /return within 30 seconds/i
          )
        ).toBeInTheDocument();
      }
    );


    it(
      "shows the cancellation message when the backend cancels the request",
      async () => {
        api.get.mockResolvedValue({
          data: {
            request: WAITING_REQUEST,
          },
        });

        api.post.mockResolvedValue({
          data: {
            active: false,
            cancelled: true,
            detail:
              "Your waiting request was cancelled because you left the waiting spot.",
          },
        });

        render(
          <PassengerLocationMonitor />
        );

        expect(
          await screen.findByText(
            /cancelled because you left/i
          )
        ).toBeInTheDocument();
      }
    );


    it(
      "shows a location access warning when GPS cannot be obtained",
      async () => {
        Object.defineProperty(
          navigator,
          "geolocation",
          {
            configurable: true,

            value: {
              getCurrentPosition:
                vi.fn((
                  success,
                  error
                ) => {
                  error(
                    new Error(
                      "Permission denied"
                    )
                  );
                }),
            },
          }
        );

        api.get.mockResolvedValue({
          data: {
            request: WAITING_REQUEST,
          },
        });

        render(
          <PassengerLocationMonitor />
        );

        expect(
          await screen.findByText(
            /please allow location access/i
          )
        ).toBeInTheDocument();

        expect(
          api.post
        ).not.toHaveBeenCalled();
      }
    );


    it(
      "revalidates again after 10 seconds",
      async () => {
        vi.useFakeTimers();

        api.get.mockResolvedValue({
          data: {
            request: WAITING_REQUEST,
          },
        });

        api.post.mockResolvedValue({
          data: {
            active: true,
            cancelled: false,
            inside_geofence: true,
            grace_period_active: false,
          },
        });

        render(
          <PassengerLocationMonitor />
        );

        await flushAsyncWork();

        expect(
          api.post
        ).toHaveBeenCalledTimes(1);


        await act(async () => {
          vi.advanceTimersByTime(
            10000
          );

          await Promise.resolve();
          await Promise.resolve();
          await Promise.resolve();
        });


        expect(
          api.post
        ).toHaveBeenCalledTimes(2);
      }
    );


    it(
      "clears the outside warning after the passenger returns inside",
      async () => {
        vi.useFakeTimers();

        api.get.mockResolvedValue({
          data: {
            request: WAITING_REQUEST,
          },
        });

        api.post
          .mockResolvedValueOnce({
            data: {
              active: true,
              cancelled: false,
              inside_geofence: false,
              grace_period_active: true,
            },
          })
          .mockResolvedValueOnce({
            data: {
              active: true,
              cancelled: false,
              inside_geofence: true,
              grace_period_active: false,
            },
          });


        render(
          <PassengerLocationMonitor />
        );

        await flushAsyncWork();

        expect(
          screen.getByText(
            /return within 30 seconds/i
          )
        ).toBeInTheDocument();


        await act(async () => {
          vi.advanceTimersByTime(
            10000
          );

          await Promise.resolve();
          await Promise.resolve();
          await Promise.resolve();
        });


        expect(
          screen.queryByText(
            /return within 30 seconds/i
          )
        ).not.toBeInTheDocument();
      }
    );
  }
);