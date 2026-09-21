const LOCATION_INTERVAL = 5000;
const ROUTE_INTERVAL = 15000;

export function startPassengerTracking({
  api,
  dispatchId,
  onLocation,
  onRoute,
  onErrors,
  onLoading,
  onUnavailable,
  timers = globalThis,
}) {
  let stopped = false;
  let locationTime = null;
  const errors = { location: "", route: "" };
  const channels = [
    {
      name: "location",
      path: "location",
      interval: LOCATION_INTERVAL,
      timeout: 10000,
      controller: new AbortController(),
      timer: null,
    },
    {
      name: "route",
      path: "passenger-route",
      interval: ROUTE_INTERVAL,
      timeout: 20000,
      controller: new AbortController(),
      timer: null,
    },
  ];

  function stop() {
    if (stopped) return;
    stopped = true;

    for (const channel of channels) {
      channel.controller.abort();
      if (channel.timer !== null) {
        timers.clearTimeout(channel.timer);
      }
    }
  }

  function updateError(name, message) {
    errors[name] = message;
    onErrors({ ...errors });
  }

  function publishLocation(location) {
    if (!location) {
      if (locationTime === null) onLocation(null);
      return;
    }

    const timestamp = Date.parse(location.updated_at);

    // A slower route response must not move the taxi to an older GPS fix.
    if (
      locationTime !== null &&
      (!Number.isFinite(timestamp) || timestamp < locationTime)
    ) {
      return;
    }

    if (Number.isFinite(timestamp)) locationTime = timestamp;
    onLocation(location);
  }

  async function poll(channel) {
    if (stopped) return;

    try {
      const response = await api.get(
        `/transport/dispatches/${dispatchId}/${channel.path}/`,
        {
          signal: channel.controller.signal,
          timeout: channel.timeout,
        }
      );

      if (stopped) return;

      if (channel.name === "location") {
        publishLocation(response.data.available ? response.data : null);
      } else {
        onRoute({
          pickupSpots: response.data.pickup_spots || [],
          route: response.data.route || null,
        });
        publishLocation(response.data.driver_location);
      }

      updateError(channel.name, "");
    } catch (error) {
      if (stopped) return;

      const status = error.response?.status;
      const unavailable =
        [401, 403, 404].includes(status) ||
        (channel.name === "location" && status === 400);

      if (unavailable) {
        stop();
        onUnavailable();
        return;
      }

      // Route 400 is ambiguous: the backend also uses it for provider outages.
      // The location endpoint independently detects an ended dispatch.
      updateError(
        channel.name,
        channel.name === "location"
          ? "Taxi location could not be refreshed. Retrying automatically."
          : "Pickup route could not be refreshed. Retrying automatically."
      );
    } finally {
      if (!stopped) {
        if (channel.name === "location") onLoading(false);

        // Schedule after completion so slow requests cannot overlap.
        channel.timer = timers.setTimeout(
          () => poll(channel),
          channel.interval
        );
      }
    }
  }

  onLoading(true);
  onErrors({ ...errors });
  for (const channel of channels) void poll(channel);

  return stop;
}
