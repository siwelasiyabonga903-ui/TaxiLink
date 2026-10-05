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
import PassengerLocationMonitor from "./PassengerLocationMonitor";

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

const INSIDE_RESPONSE = {
  active: true,
  cancelled: false,
  inside_geofence: true,
  grace_period_active: false,
  grace_seconds_remaining: 0,
};

const OUTSIDE_RESPONSE = {
  active: true,
  cancelled: false,
  inside_geofence: false,
  grace_period_active: true,
  grace_seconds_remaining: 60,
};

function setSuccessfulLocation() {
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: {
      getCurrentPosition: vi.fn((success) => {
        success({
          coords: {
            latitude: -23.8845,
            longitude: 29.7382,
          },
        });
      }),
    },
  });
}

async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("PassengerLocationMonitor", () => {
  let previousGeolocation;

  beforeEach(() => {
    vi.resetAllMocks();

    previousGeolocation = Object.getOwnPropertyDescriptor(
      navigator,
      "geolocation"
    );

    setSuccessfulLocation();

    api.get.mockResolvedValue({
      data: { request: WAITING_REQUEST },
    });

    api.post.mockResolvedValue({
      data: INSIDE_RESPONSE,
    });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();

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
    "does not request GPS when there is no active waiting request",
    async () => {
      api.get.mockResolvedValue({
        data: { request: null },
      });

      render(<PassengerLocationMonitor />);
      await flushAsyncWork();

      expect(api.get).toHaveBeenCalledTimes(1);

      expect(
        navigator.geolocation.getCurrentPosition
      ).not.toHaveBeenCalled();

      expect(api.post).not.toHaveBeenCalled();
    }
  );

  it(
    "revalidates the passenger location when waiting",
    async () => {
      render(<PassengerLocationMonitor />);

      await waitFor(() => {
        expect(api.post).toHaveBeenCalledWith(
          "/transport/waiting-requests/revalidate-location/",
          {
            latitude: "-23.884500",
            longitude: "29.738200",
          }
        );
      });

      expect(
        screen.queryByText(/outside the waiting spot/i)
      ).not.toBeInTheDocument();
    }
  );

  it(
    "shows a warning while the geofence grace period is active",
    async () => {
      api.post.mockResolvedValue({
        data: OUTSIDE_RESPONSE,
      });

      render(<PassengerLocationMonitor />);

      expect(
        await screen.findByText(/return within 60 seconds/i)
      ).toBeInTheDocument();
    }
  );

  it(
    "shows the cancellation message when the backend cancels the request",
    async () => {
      api.post.mockResolvedValue({
        data: {
          active: false,
          cancelled: true,
          detail:
            "Your waiting request was cancelled because you left the waiting spot.",
        },
      });

      render(<PassengerLocationMonitor />);

      expect(
        await screen.findByText(/cancelled because you left/i)
      ).toBeInTheDocument();
    }
  );

  it(
    "shows a location access warning when GPS cannot be obtained",
    async () => {
      navigator.geolocation.getCurrentPosition.mockImplementation(
        (success, error) => {
          error(new Error("Permission denied"));
        }
      );

      render(<PassengerLocationMonitor />);

      expect(
        await screen.findByText(/please allow location access/i)
      ).toBeInTheDocument();

      expect(api.post).not.toHaveBeenCalled();
    }
  );

  it("revalidates again after 10 seconds", async () => {
    vi.useFakeTimers();

    render(<PassengerLocationMonitor />);
    await flushAsyncWork();

    expect(api.post).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });

    expect(api.post).toHaveBeenCalledTimes(2);
  });

  it(
    "clears the outside warning after the passenger returns inside",
    async () => {
      vi.useFakeTimers();

      api.post
        .mockResolvedValueOnce({
          data: OUTSIDE_RESPONSE,
        })
        .mockResolvedValueOnce({
          data: INSIDE_RESPONSE,
        });

      render(<PassengerLocationMonitor />);
      await flushAsyncWork();

      expect(
        screen.getByText(/return within 60 seconds/i)
      ).toBeInTheDocument();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });

      expect(
        screen.queryByText(/return within 60 seconds/i)
      ).not.toBeInTheDocument();
    }
  );

  it.each([
    "visibilitychange",
    "focus",
    "pageshow",
    "online",
  ])(
    "revalidates immediately on %s without overlapping checks",
    async (eventName) => {
      vi.spyOn(document, "visibilityState", "get")
        .mockReturnValue("visible");

      render(<PassengerLocationMonitor />);
      await flushAsyncWork();

      expect(api.post).toHaveBeenCalledTimes(1);

      const target =
        eventName === "visibilitychange"
          ? document
          : window;

      await act(async () => {
        target.dispatchEvent(new Event(eventName));
        target.dispatchEvent(new Event(eventName));
      });

      expect(api.get).toHaveBeenCalledTimes(2);
      expect(api.post).toHaveBeenCalledTimes(2);

      expect(
        navigator.geolocation.getCurrentPosition
      ).toHaveBeenLastCalledWith(
        expect.any(Function),
        expect.any(Function),
        expect.objectContaining({
          maximumAge: 0,
        })
      );
    }
  );

  it("counts down between location checks", async () => {
    vi.useFakeTimers();

    api.post.mockResolvedValue({
      data: OUTSIDE_RESPONSE,
    });

    render(<PassengerLocationMonitor />);
    await flushAsyncWork();

    expect(
      screen.getByText(/return within 60 seconds/i)
    ).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(
      screen.getByText(/return within 57 seconds/i)
    ).toBeInTheDocument();

    expect(api.post).toHaveBeenCalledTimes(1);
  });

  it("uses the backend remaining time on the next check", async () => {
    vi.useFakeTimers();

    api.post
      .mockResolvedValueOnce({
        data: OUTSIDE_RESPONSE,
      })
      .mockResolvedValueOnce({
        data: {
          ...OUTSIDE_RESPONSE,
          grace_seconds_remaining: 23,
        },
      });

    render(<PassengerLocationMonitor />);
    await flushAsyncWork();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });

    expect(
      screen.getByText(/return within 23 seconds/i)
    ).toBeInTheDocument();

    expect(api.post).toHaveBeenCalledTimes(2);
  });

  it("stops on return and starts 60 seconds on a new exit", async () => {
    vi.useFakeTimers();

    api.post
      .mockResolvedValueOnce({
        data: OUTSIDE_RESPONSE,
      })
      .mockResolvedValueOnce({
        data: INSIDE_RESPONSE,
      })
      .mockResolvedValueOnce({
        data: OUTSIDE_RESPONSE,
      });

    render(<PassengerLocationMonitor />);
    await flushAsyncWork();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(
      screen.getByText(/return within 57 seconds/i)
    ).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(7000);
    });

    expect(
      screen.queryByText(/return within/i)
    ).not.toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });

    expect(
      screen.getByText(/return within 60 seconds/i)
    ).toBeInTheDocument();

    expect(api.post).toHaveBeenCalledTimes(3);
  });

  it("waits for backend confirmation when the countdown reaches zero", async () => {
    vi.useFakeTimers();

    api.post.mockResolvedValue({
      data: {
        ...OUTSIDE_RESPONSE,
        grace_seconds_remaining: 1,
      },
    });

    render(<PassengerLocationMonitor />);
    await flushAsyncWork();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(
      screen.getByText(/waiting for location verification/i)
    ).toBeInTheDocument();

    expect(
      screen.queryByText(/cancelled/i)
    ).not.toBeInTheDocument();

    expect(api.post).toHaveBeenCalledTimes(1);
  });

  it("keeps the countdown visible when a network check fails", async () => {
    vi.useFakeTimers();

    api.post
      .mockResolvedValueOnce({
        data: OUTSIDE_RESPONSE,
      })
      .mockRejectedValueOnce(
        new Error("Temporary network failure")
      );

    render(<PassengerLocationMonitor />);
    await flushAsyncWork();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });

    expect(
      screen.getByText(/could not verify your waiting location/i)
    ).toBeInTheDocument();

    expect(
      screen.getByText(/return within 50 seconds/i)
    ).toBeInTheDocument();
  });

  it("accounts for elapsed time while timer callbacks are paused", async () => {
    vi.useFakeTimers();

    api.post.mockResolvedValue({
      data: OUTSIDE_RESPONSE,
    });

    render(<PassengerLocationMonitor />);
    await flushAsyncWork();

    vi.setSystemTime(Date.now() + 20000);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(
      screen.getByText(/return within 39 seconds/i)
    ).toBeInTheDocument();

    expect(api.post).toHaveBeenCalledTimes(1);
  });

  it(
    "removes resume listeners and polling on unmount",
    async () => {
      vi.useFakeTimers();

      vi.spyOn(document, "visibilityState", "get")
        .mockReturnValue("visible");

      api.get.mockResolvedValue({
        data: { request: null },
      });

      const view = render(<PassengerLocationMonitor />);
      await flushAsyncWork();

      expect(api.get).toHaveBeenCalledTimes(1);

      view.unmount();

      await act(async () => {
        document.dispatchEvent(
          new Event("visibilitychange")
        );

        for (const eventName of [
          "focus",
          "pageshow",
          "online",
        ]) {
          window.dispatchEvent(new Event(eventName));
        }

        await vi.advanceTimersByTimeAsync(10000);
      });

      expect(api.get).toHaveBeenCalledTimes(1);
    }
  );
});