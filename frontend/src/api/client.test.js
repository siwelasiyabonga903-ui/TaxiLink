// @vitest-environment jsdom

import axios from "axios";
import { waitFor } from "@testing-library/react";
import {
  afterEach,
  expect,
  it,
  vi,
} from "vitest";

import api from "./client";

const originalAdapter = api.defaults.adapter;

afterEach(() => {
  api.defaults.adapter = originalAdapter;
  vi.restoreAllMocks();
  localStorage.clear();
});

it("keeps tokens after a refresh outage and refreshes on the next request", async () => {
  localStorage.setItem("access_token", "old-access");
  localStorage.setItem("refresh_token", "refresh-token");

  api.defaults.adapter = vi.fn((config) => {
    if (
      config.headers.get("Authorization")
      === "Bearer old-access"
    ) {
      return Promise.reject({
        config,
        response: { status: 401, data: {} },
      });
    }

    return Promise.resolve({
      config,
      status: 200,
      statusText: "OK",
      headers: {},
      data: { id: 7 },
    });
  });

  const refresh = vi.spyOn(axios, "post")
    .mockRejectedValueOnce(
      new Error("Temporary outage")
    )
    .mockResolvedValueOnce({
      data: { access: "new-access" },
    });

  await expect(
    api.get("/accounts/me/")
  ).rejects.toThrow("Temporary outage");

  expect(localStorage.getItem("access_token"))
    .toBe("old-access");

  expect(localStorage.getItem("refresh_token"))
    .toBe("refresh-token");

  await expect(
    api.get("/accounts/me/")
  ).resolves.toMatchObject({
    data: { id: 7 },
  });

  expect(refresh).toHaveBeenCalledTimes(2);

  expect(localStorage.getItem("access_token"))
    .toBe("new-access");
});

it("shares one refresh between simultaneous expired requests", async () => {
  localStorage.setItem(
    "access_token",
    "expired-access"
  );
  localStorage.setItem(
    "refresh_token",
    "shared-refresh"
  );

  api.defaults.adapter = vi.fn((config) => {
    if (
      config.headers.get("Authorization")
      === "Bearer expired-access"
    ) {
      return Promise.reject({
        config,
        response: { status: 401, data: {} },
      });
    }

    return Promise.resolve({
      config,
      status: 200,
      statusText: "OK",
      headers: {},
      data: { url: config.url },
    });
  });

  let finishRefresh;

  const refresh = vi.spyOn(
    axios,
    "post"
  ).mockImplementation(
    () => new Promise((resolve) => {
      finishRefresh = resolve;
    })
  );

  const firstRequest = api.get(
    "/transport/dispatches/"
  );
  const secondRequest = api.get(
    "/transport/routes/"
  );

  await waitFor(() => {
    expect(
      api.defaults.adapter
    ).toHaveBeenCalledTimes(2);

    expect(refresh).toHaveBeenCalledTimes(1);
  });

  finishRefresh({
    data: {
      access: "fresh-access",
    },
  });

  const [first, second] = await Promise.all([
    firstRequest,
    secondRequest,
  ]);

  expect(first.data.url).toBe(
    "/transport/dispatches/"
  );
  expect(second.data.url).toBe(
    "/transport/routes/"
  );

  expect(refresh).toHaveBeenCalledTimes(1);

  expect(
    localStorage.getItem("access_token")
  ).toBe("fresh-access");
});