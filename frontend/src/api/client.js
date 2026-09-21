import axios from "axios";

const baseURL = import.meta.env.VITE_API_BASE_URL;

const api = axios.create({
  baseURL,
  headers: {
    "Content-Type": "application/json",
  },
});

let sessionId = 0;
let knownAccessToken = null;
let knownRefreshToken = null;
let refreshInFlight = null;

function currentSession() {
  const accessToken = localStorage.getItem("access_token");
  const refreshToken = localStorage.getItem("refresh_token");

  // Login/logout changes invalidate requests from the previous session.
  if (
    accessToken !== knownAccessToken ||
    refreshToken !== knownRefreshToken
  ) {
    sessionId += 1;
    knownAccessToken = accessToken;
    knownRefreshToken = refreshToken;
  }

  return { id: sessionId, accessToken, refreshToken };
}

function endSession(expectedId) {
  if (currentSession().id !== expectedId) {
    return;
  }

  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  currentSession();
  window.location.href = "/login";
}

function validToken(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function refreshAccess(session) {
  if (refreshInFlight?.sessionId === session.id) {
    return refreshInFlight.promise;
  }

  const pending = { sessionId: session.id, promise: null };
  refreshInFlight = pending;

  pending.promise = Promise.resolve()
    .then(async () => {
      try {
        const response = await axios.post(
          "/accounts/token/refresh/",
          { refresh: session.refreshToken },
          { baseURL, timeout: 15000 }
        );

        if (currentSession().id !== session.id) {
          throw new Error("Your session changed while refreshing.");
        }

        const accessToken = response.data?.access;
        const refreshToken = response.data?.refresh;

        if (
          !validToken(accessToken) ||
          (refreshToken !== undefined && !validToken(refreshToken))
        ) {
          const invalidResponse = new Error(
            "Token refresh returned an invalid response."
          );
          invalidResponse.invalidRefreshResponse = true;
          throw invalidResponse;
        }

        localStorage.setItem("access_token", accessToken);
        knownAccessToken = accessToken;

        // Preserve a replacement refresh token if the server returns one.
        if (refreshToken !== undefined) {
          localStorage.setItem("refresh_token", refreshToken);
          knownRefreshToken = refreshToken;
        }
      } catch (error) {
        if (
          [400, 401, 403].includes(error?.response?.status) ||
          error?.invalidRefreshResponse === true
        ) {
          endSession(session.id);
        }

        throw error;
      }
    })
    .finally(() => {
      if (refreshInFlight === pending) {
        refreshInFlight = null;
      }
    });

  return pending.promise;
}

api.interceptors.request.use((config) => {
  const session = currentSession();

  if (config._retry && config._authSessionId !== session.id) {
    throw new Error("Your session changed before the request could retry.");
  }

  config._authSessionId = session.id;
  config._authAccessToken = session.accessToken;
  config.headers.Authorization = session.accessToken
    ? `Bearer ${session.accessToken}`
    : undefined;

  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const url = originalRequest?.url || "";

    if (
      error.response?.status !== 401 ||
      !originalRequest ||
      url.includes("/accounts/login/") ||
      url.includes("/accounts/token/refresh/")
    ) {
      throw error;
    }

    const session = currentSession();

    if (originalRequest._authSessionId !== session.id) {
      throw error;
    }

    if (originalRequest._retry || !session.refreshToken) {
      endSession(session.id);
      throw error;
    }

    originalRequest._retry = true;

    // Another request may already have refreshed this expired token.
    if (
      !session.accessToken ||
      originalRequest._authAccessToken === session.accessToken
    ) {
      await refreshAccess(session);
    }

    if (currentSession().id !== session.id) {
      throw error;
    }

    return api(originalRequest);
  }
);

export default api;