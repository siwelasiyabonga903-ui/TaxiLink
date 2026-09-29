// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import {
  cleanup,
  render,
  screen,
} from "@testing-library/react";

import {
  afterEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  MemoryRouter,
} from "react-router-dom";

import AppLayout from "./AppLayout";


const { mockUseAuth } = vi.hoisted(
  () => ({
    mockUseAuth: vi.fn(),
  })
);


vi.mock(
  "../context/AuthContext",
  () => ({
    useAuth: mockUseAuth,
  })
);


vi.mock(
  "./PassengerLocationMonitor",
  () => ({
    default: () => (
      <div data-testid="passenger-location-monitor">
        Passenger location monitor
      </div>
    ),
  })
);

vi.mock(
  "./NotificationCenter",
  () => ({
    default: () => (
      <div data-testid="notification-center">
        Notification center
      </div>
    ),
  })
);

function renderLayout(user) {
  mockUseAuth.mockReturnValue({
    user,
    logout: vi.fn(),
  });

  return render(
    <MemoryRouter>
      <AppLayout>
        <div>Page content</div>
      </AppLayout>
    </MemoryRouter>
  );
}


describe(
  "AppLayout passenger monitoring",
  () => {
    afterEach(() => {
      cleanup();

      vi.clearAllMocks();
    });


    it(
      "mounts the location monitor for passengers",
      () => {
        renderLayout({
          username: "passenger1",
          role: "PASSENGER",
          role_display: "Passenger",
        });

        expect(
          screen.getByTestId(
            "passenger-location-monitor"
          )
        ).toBeInTheDocument();
      }
    );


    it(
      "does not mount the location monitor for drivers",
      () => {
        renderLayout({
          username: "driver1",
          role: "DRIVER",
          role_display: "Driver",
        });

        expect(
          screen.queryByTestId(
            "passenger-location-monitor"
          )
        ).not.toBeInTheDocument();
      }
    );


    it(
      "does not mount the location monitor for dispatchers",
      () => {
        renderLayout({
          username: "dispatcher1",
          role: "DISPATCHER",
          role_display: "Dispatcher",
        });

        expect(
          screen.queryByTestId(
            "passenger-location-monitor"
          )
        ).not.toBeInTheDocument();
      }
    );
  }
);