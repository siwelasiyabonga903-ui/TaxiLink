// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import {
  act,
  cleanup,
  render,
  screen,
} from "@testing-library/react";

import {
  afterEach,
  beforeEach,
  expect,
  it,
  vi,
} from "vitest";

import api from "../api/client";
import {
  AuthProvider,
  useAuth,
} from "./AuthContext";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
  },
}));

function SessionStatus() {
  const { user, loading } = useAuth();

  return (
    <div data-testid="session-status">
      {loading
        ? "Loading session"
        : user?.role || "Signed out"}
    </div>
  );
}

beforeEach(() => {
  vi.useFakeTimers();
  api.get.mockReset();
  localStorage.clear();
  localStorage.setItem("access_token", "access-token");
  localStorage.setItem("refresh_token", "refresh-token");
});

afterEach(() => {
  cleanup();
  vi.clearAllTimers();
  vi.useRealTimers();
  localStorage.clear();
});

it("preserves the session during an outage and loads it when service returns", async () => {
  api.get
    .mockRejectedValueOnce(new Error("Offline"))
    .mockResolvedValueOnce({
      data: { role: "DRIVER" },
    });

  await act(async () => {
    render(
      <AuthProvider>
        <SessionStatus />
      </AuthProvider>
    );
  });

  expect(screen.getByTestId("session-status"))
    .toHaveTextContent("Loading session");

  expect(localStorage.getItem("access_token"))
    .toBe("access-token");

  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000);
  });

  expect(screen.getByTestId("session-status"))
    .toHaveTextContent("DRIVER");

  expect(api.get).toHaveBeenCalledTimes(2);
});

it("clears tokens when the profile request is unauthorized", async () => {
  api.get.mockRejectedValueOnce({
    response: { status: 401 },
  });

  await act(async () => {
    render(
      <AuthProvider>
        <SessionStatus />
      </AuthProvider>
    );
  });

  expect(screen.getByTestId("session-status"))
    .toHaveTextContent("Signed out");

  expect(localStorage.getItem("access_token"))
    .toBeNull();

  expect(localStorage.getItem("refresh_token"))
    .toBeNull();
});

it("cancels a scheduled retry when the provider unmounts", async () => {
  api.get.mockRejectedValue(new Error("Offline"));

  let view;

  await act(async () => {
    view = render(
      <AuthProvider>
        <SessionStatus />
      </AuthProvider>
    );
  });

  view.unmount();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000);
  });

  expect(api.get).toHaveBeenCalledTimes(1);
});