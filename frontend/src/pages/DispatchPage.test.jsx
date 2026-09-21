// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import {
  act,
  cleanup,
  render,
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
import DispatchPage from "./DispatchPage";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock("../components/AppLayout", () => ({
  default: ({ children }) => (
    <div>{children}</div>
  ),
}));

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({
    user: {
      role: "DRIVER",
    },
  }),
}));

const EN_ROUTE_ASSIGNMENT = {
  id: 7,
  route_name: "Campus to Town",
  passenger_count: 2,
  status: "EN_ROUTE",
  status_display: "En route",
  notes: "",
  created_at: "2026-09-19T10:00:00Z",
  pickup_spots: [],
};

describe("DispatchPage live location", () => {
  let previousGeolocation;

  beforeEach(() => {
    vi.clearAllMocks();

    previousGeolocation =
      Object.getOwnPropertyDescriptor(
        navigator,
        "geolocation"
      );

    api.get.mockResolvedValue({
      data: [EN_ROUTE_ASSIGNMENT],
    });

    api.post.mockResolvedValue({
      data: {},
    });

    Object.defineProperty(
      navigator,
      "geolocation",
      {
        configurable: true,
        value: {
          watchPosition: vi.fn((success) => {
            success({
              coords: {
                latitude: -23.8845,
                longitude: 29.7382,
                accuracy: 8.5,
              },
            });

            return 42;
          }),
          clearWatch: vi.fn(),
        },
      }
    );
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();

    if (previousGeolocation) {
      Object.defineProperty(
        navigator,
        "geolocation",
        previousGeolocation
      );
    } else {
      delete navigator.geolocation;
    }
  });

  it(
    "sends driver location for an en route dispatch",
    async () => {
      render(<DispatchPage />);

      await waitFor(() => {
        expect(api.post).toHaveBeenCalledWith(
          "/transport/dispatches/7/location/",
          {
            latitude: "-23.884500",
            longitude: "29.738200",
            accuracy_meters: "8.50",
          }
        );
      });
    }
  );

  it(
    "does not start tracking for a pending dispatch",
    async () => {
      api.get.mockResolvedValue({
        data: [
          {
            ...EN_ROUTE_ASSIGNMENT,
            status: "PENDING",
            status_display: "Pending",
          },
        ],
      });

      render(<DispatchPage />);

      await waitFor(() => {
        expect(api.get).toHaveBeenCalled();
      });

      expect(
        navigator.geolocation.watchPosition
      ).not.toHaveBeenCalled();
    }
  );

  it(
    "clears the location watcher when the page unmounts",
    async () => {
      const { unmount } = render(
        <DispatchPage />
      );

      await waitFor(() => {
        expect(
          navigator.geolocation.watchPosition
        ).toHaveBeenCalled();
      });

      unmount();

      expect(
        navigator.geolocation.clearWatch
      ).toHaveBeenCalledWith(42);
    }
  );

  it(
    "retries a failed location POST without a new GPS event",
    async () => {
      vi.useFakeTimers();

      api.post.mockRejectedValueOnce(
        new Error("Temporary network failure")
      );

      await act(async () => {
        render(<DispatchPage />);
      });

      expect(api.post).toHaveBeenCalledTimes(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });

      expect(api.post).toHaveBeenCalledTimes(2);

      expect(api.post.mock.calls[1][0]).toBe(
        "/transport/dispatches/7/location/"
      );

      expect(api.post.mock.calls[1][1]).toEqual(
        api.post.mock.calls[0][1]
      );
    }
  );

  it(
    "ignores a queued GPS callback after unmount",
    async () => {
      vi.useFakeTimers();

      let view;

      await act(async () => {
        view = render(<DispatchPage />);
      });

      expect(api.post).toHaveBeenCalledTimes(1);

      const onPosition =
        navigator.geolocation
          .watchPosition.mock.calls[0][0];

      view.unmount();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);

        await onPosition({
          coords: {
            latitude: -23.8845,
            longitude: 29.7382,
            accuracy: 8.5,
          },
        });
      });

      expect(api.post).toHaveBeenCalledTimes(1);

      expect(
        navigator.geolocation.clearWatch
      ).toHaveBeenCalledWith(42);
    }
  );

  it(
    "restarts GPS sharing when the dispatch page is reopened",
    async () => {
      const firstPage = render(
        <DispatchPage />
      );

      await waitFor(() => {
        expect(
          navigator.geolocation.watchPosition
        ).toHaveBeenCalledTimes(1);

        expect(api.post).toHaveBeenCalledTimes(1);
      });

      firstPage.unmount();

      expect(
        navigator.geolocation.clearWatch
      ).toHaveBeenCalledWith(42);

      api.post.mockClear();

      const secondPage = render(
        <DispatchPage />
      );

      await waitFor(() => {
        expect(
          navigator.geolocation.watchPosition
        ).toHaveBeenCalledTimes(2);

        expect(api.post).toHaveBeenCalledWith(
          "/transport/dispatches/7/location/",
          expect.objectContaining({
            latitude: "-23.884500",
            longitude: "29.738200",
          })
        );
      });

      secondPage.unmount();

      expect(
        navigator.geolocation.clearWatch
      ).toHaveBeenCalledTimes(2);
    }
  );
});