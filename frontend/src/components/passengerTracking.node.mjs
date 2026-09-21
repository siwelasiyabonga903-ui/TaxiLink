import test from "node:test";
import assert from "node:assert/strict";
import { setImmediate } from "node:timers";
import { startPassengerTracking } from "./passengerTracking.mjs";

const settle = () => new Promise((resolve) => setImmediate(resolve));

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function fail(status) {
  const error = new Error(status ? `HTTP ${status}` : "Network unavailable");
  if (status) error.response = { status };
  throw error;
}

function location(seconds = 1) {
  return {
    available: true,
    latitude: -23.88,
    longitude: 29.73 + seconds / 1000,
    updated_at: new Date(Date.UTC(2026, 0, 1, 0, 0, seconds)).toISOString(),
  };
}

function routeResponse(seconds = 1) {
  const fix = location(seconds);
  return {
    available: true,
    driver_location: fix,
    pickup_spots: [{
      id: 3,
      is_passenger_spot: true,
      name: "Campus",
      latitude: -23.89,
      longitude: 29.74,
    }],
    route: {
      type: "FeatureCollection",
      features: [{
        type: "Feature",
        properties: {},
        geometry: {
          type: "LineString",
          coordinates: [[fix.longitude, fix.latitude], [29.74, -23.89]],
        },
      }],
    },
  };
}

function setup() {
  let nextTimer = 0;
  const jobs = new Map();
  const calls = [];
  const events = [];
  const state = {
    location: null,
    route: null,
    errors: {},
    loading: null,
    closed: 0,
  };
  const handlers = {
    location: async () => location(),
    route: async () => routeResponse(),
  };

  const options = {
    dispatchId: 7,
    api: {
      get: async (url, config) => {
        const name = url.endsWith("/passenger-route/") ? "route" : "location";
        calls.push({ name, url, config });
        return { data: await handlers[name]() };
      },
    },
    timers: {
      setTimeout(callback, delay) {
        const id = ++nextTimer;
        jobs.set(id, { callback, delay });
        return id;
      },
      clearTimeout(id) { jobs.delete(id); },
    },
    onLocation(value) { state.location = value; events.push("location"); },
    onRoute(value) { state.route = value; events.push("route"); },
    onErrors(value) { state.errors = value; events.push("errors"); },
    onLoading(value) { state.loading = value; events.push("loading"); },
    onUnavailable() { state.closed += 1; events.push("closed"); },
  };

  return {
    state, handlers, calls, events, jobs,
    start: () => startPassengerTracking(options),
    async tick(delay) {
      const ready = [...jobs.entries()].filter(([, job]) => job.delay === delay);
      for (const [id, job] of ready) {
        jobs.delete(id);
        job.callback();
      }
      await settle();
    },
  };
}

test("routing-provider 400 keeps tracking open and location polling alive", async (t) => {
  const h = setup();
  h.handlers.route = async () => fail(400);
  t.after(h.start());
  await settle();

  assert.equal(h.state.closed, 0);
  assert.ok(h.state.errors.route);
  assert.equal(h.state.errors.location, "");
  assert.ok(h.state.location);
  assert.equal(h.state.loading, false);

  h.handlers.location = async () => location(2);
  await h.tick(5000);
  assert.equal(h.state.location.updated_at, location(2).updated_at);
  assert.ok(h.state.errors.route, "A GPS success must not erase the route error.");
  assert.equal(h.state.closed, 0);
});

test("a route outage preserves the last route and recovers automatically", async (t) => {
  const h = setup();
  t.after(h.start());
  await settle();
  const previousRoute = h.state.route;

  h.handlers.route = async () => fail(400);
  await h.tick(15000);
  assert.equal(h.state.route, previousRoute);
  assert.ok(h.state.errors.route);

  h.handlers.route = async () => routeResponse(5);
  await h.tick(15000);
  assert.equal(h.state.errors.route, "");
  assert.notEqual(h.state.route, previousRoute);
  assert.equal(h.state.location.updated_at, location(5).updated_at);
  assert.equal(h.state.closed, 0);
});

test("temporary GPS failure keeps the last fix and the next poll recovers", async (t) => {
  const h = setup();
  t.after(h.start());
  await settle();
  const previousFix = h.state.location;

  h.handlers.location = async () => fail(503);
  await h.tick(5000);
  assert.equal(h.state.location, previousFix);
  assert.ok(h.state.errors.location);

  await h.tick(15000);
  assert.ok(h.state.errors.location, "A route success must not erase a GPS error.");

  h.handlers.location = async () => location(4);
  await h.tick(5000);
  assert.equal(h.state.location.updated_at, location(4).updated_at);
  assert.equal(h.state.errors.location, "");
  assert.equal(h.state.closed, 0);
});

test("network failures stay retryable on both endpoints", async (t) => {
  const h = setup();
  h.handlers.location = h.handlers.route = async () => fail();
  t.after(h.start());
  await settle();

  assert.equal(h.state.closed, 0);
  assert.ok(h.state.errors.location);
  assert.ok(h.state.errors.route);
  assert.equal(h.jobs.size, 2);

  h.handlers.location = async () => location();
  h.handlers.route = async () => routeResponse();
  await h.tick(5000);
  await h.tick(15000);
  assert.deepEqual(h.state.errors, { location: "", route: "" });
});

test("no GPS yet stays open and later receives the driver's first fix", async (t) => {
  const h = setup();
  h.handlers.location = async () => ({ available: false });
  h.handlers.route = async () => ({
    available: false, driver_location: null, pickup_spots: [], route: null,
  });
  t.after(h.start());
  await settle();

  assert.equal(h.state.location, null);
  assert.equal(h.state.loading, false);
  assert.equal(h.state.closed, 0);
  assert.deepEqual(h.state.errors, { location: "", route: "" });

  h.handlers.location = async () => location();
  await h.tick(5000);
  assert.ok(h.state.location);
});

test("ended dispatch and revoked access stop polling and close once", async () => {
  const scenarios = [
    ["location", 400], ["location", 401], ["location", 403], ["location", 404],
    ["route", 401], ["route", 403], ["route", 404],
  ];

  for (const [endpoint, status] of scenarios) {
    const h = setup();
    h.handlers[endpoint] = async () => fail(status);
    const stop = h.start();
    await settle();
    assert.equal(h.state.closed, 1, `${endpoint} ${status}`);
    assert.equal(h.jobs.size, 0);
    assert.ok(h.calls.every((call) => call.config.signal.aborted));
    const count = h.calls.length;
    await h.tick(5000);
    await h.tick(15000);
    assert.equal(h.calls.length, count);
    stop();
  }
});

test("simultaneous permission errors close only once", async () => {
  const h = setup();
  h.handlers.location = h.handlers.route = async () => fail(403);
  const stop = h.start();
  await settle();
  assert.equal(h.state.closed, 1);
  assert.equal(h.jobs.size, 0);
  stop();
});

test("cleanup aborts requests and ignores late responses", async () => {
  const h = setup();
  const gps = deferred();
  const route = deferred();
  h.handlers.location = () => gps.promise;
  h.handlers.route = () => route.promise;
  const stop = h.start();

  assert.equal(h.calls.length, 2);
  stop();
  const eventCount = h.events.length;
  gps.resolve(location());
  route.resolve(routeResponse());
  await settle();

  assert.equal(h.events.length, eventCount);
  assert.equal(h.jobs.size, 0);
  assert.ok(h.calls.every((call) => call.config.signal.aborted));
  assert.equal(h.state.closed, 0, "Unmounting must not call onClose again.");
});

test("cleanup removes scheduled polling", async () => {
  const h = setup();
  const stop = h.start();
  await settle();
  assert.equal(h.jobs.size, 2);
  stop();
  assert.equal(h.jobs.size, 0);
  await h.tick(5000);
  await h.tick(15000);
  assert.equal(h.calls.length, 2);
});

test("slow requests never overlap within either polling channel", async (t) => {
  const h = setup();
  const gps = deferred();
  const route = deferred();
  h.handlers.location = () => gps.promise;
  h.handlers.route = () => route.promise;
  t.after(h.start());

  for (let n = 0; n < 4; n += 1) {
    await h.tick(5000);
    await h.tick(15000);
  }
  assert.equal(h.calls.length, 2);

  gps.resolve(location());
  route.resolve(routeResponse());
  await settle();
  assert.equal(h.jobs.size, 2);
});

test("a slower route response cannot rewind a newer GPS fix", async (t) => {
  const h = setup();
  const route = deferred();
  h.handlers.location = async () => location(10);
  h.handlers.route = () => route.promise;
  t.after(h.start());
  await settle();
  route.resolve(routeResponse(1));
  await settle();

  assert.equal(h.state.location.updated_at, location(10).updated_at);
  assert.ok(h.state.route);
});

test("a late no-location response cannot remove an already received fix", async (t) => {
  const h = setup();
  const gps = deferred();
  h.handlers.location = () => gps.promise;
  h.handlers.route = async () => routeResponse(10);
  t.after(h.start());
  await settle();
  gps.resolve({ available: false });
  await settle();

  assert.equal(h.state.location.updated_at, location(10).updated_at);
});

test("a fresh start after cleanup resumes both polling channels", async () => {
  const h = setup();
  const stopFirst = h.start();
  await settle();
  stopFirst();

  const stopSecond = h.start();
  await settle();
  assert.equal(h.calls.length, 4);
  assert.equal(h.jobs.size, 2);
  assert.ok(h.calls.slice(0, 2).every((call) => call.config.signal.aborted));
  assert.ok(h.calls.slice(2).every((call) => !call.config.signal.aborted));
  stopSecond();
  assert.equal(h.jobs.size, 0);
});
