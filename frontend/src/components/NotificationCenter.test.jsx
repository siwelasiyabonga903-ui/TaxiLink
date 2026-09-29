// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import {
  act,
  cleanup,
  fireEvent,
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
import NotificationCenter from "./NotificationCenter";


vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));


const NOTIFICATIONS = [
  {
    id: 21,
    notification_type: "NEW_DISPATCH",
    title: "New dispatch",
    message:
      "You have been assigned to Campus to Town.",
    dispatch: 7,
    is_read: false,
    created_at: "2026-09-29T15:30:00Z",
  },
  {
    id: 20,
    notification_type: "DISPATCH_ACCEPTED",
    title: "Dispatch accepted",
    message: "Driver1 accepted the dispatch.",
    dispatch: 6,
    is_read: true,
    created_at: "2026-09-29T14:30:00Z",
  },
];


describe("NotificationCenter", () => {
  beforeEach(() => {
    api.get.mockResolvedValue({
      data: NOTIFICATIONS,
    });

    api.post.mockResolvedValue({
      data: {},
    });
  });


  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });


  it(
    "loads notifications and shows the unread count",
    async () => {
      render(
        <NotificationCenter
          pushState="unavailable"
        />
      );

      const bell = await screen.findByRole(
        "button",
        {
          name: "1 unread notifications",
        }
      );

      expect(api.get).toHaveBeenCalledWith(
        "/transport/notifications/"
      );

      fireEvent.click(bell);

      expect(
        screen.getByText("New dispatch")
      ).toBeInTheDocument();

      expect(
        screen.getByText(
          /In-app notifications are still active/i
        )
      ).toBeInTheDocument();
    }
  );

  it(
  "closes the panel and returns focus to the notification bell",
  async () => {
    render(
      <NotificationCenter />
    );

    const bell =
      await screen.findByRole(
        "button",
        {
          name:
            "1 unread notifications",
        }
      );

    fireEvent.click(bell);

    expect(
      screen.getByRole(
        "region",
        {
          name:
            "TaxiLink notifications",
        }
      )
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole(
        "button",
        {
          name:
            "Close notifications",
        }
      )
    );

    expect(
      screen.queryByRole(
        "region",
        {
          name:
            "TaxiLink notifications",
        }
      )
    ).not.toBeInTheDocument();

    expect(bell).toHaveFocus();
  }
);

  it(
    "marks one notification as read",
    async () => {
      render(<NotificationCenter />);

      const bell = await screen.findByRole(
        "button",
        {
          name: "1 unread notifications",
        }
      );

      fireEvent.click(bell);

      fireEvent.click(
        screen.getByRole(
          "button",
          {
            name: /New dispatch/i,
          }
        )
      );

      await waitFor(() => {
        expect(api.post).toHaveBeenCalledWith(
          "/transport/notifications/21/read/"
        );
      });

      expect(
        screen.getByRole(
          "button",
          {
            name: "Notifications",
          }
        )
      ).toBeInTheDocument();
    }
  );


  it(
    "marks every unread notification as read",
    async () => {
      api.get.mockResolvedValue({
        data: NOTIFICATIONS.map(
          (notification) => ({
            ...notification,
            is_read: false,
          })
        ),
      });

      render(<NotificationCenter />);

      const bell = await screen.findByRole(
        "button",
        {
          name: "2 unread notifications",
        }
      );

      fireEvent.click(bell);

      fireEvent.click(
        screen.getByRole(
          "button",
          {
            name: "Mark all read",
          }
        )
      );

      await waitFor(() => {
        expect(api.post).toHaveBeenCalledWith(
          "/transport/notifications/read-all/"
        );
      });

      expect(
        screen.getByRole(
          "button",
          {
            name: "Notifications",
          }
        )
      ).toBeInTheDocument();
    }
  );


  it(
    "does not overlap notification refresh requests",
    async () => {
      let resolveRequest;

      api.get.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveRequest = resolve;
          })
      );

      render(<NotificationCenter />);

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledTimes(1);
      });

      act(() => {
        window.dispatchEvent(
          new Event("focus")
        );
      });

      expect(api.get).toHaveBeenCalledTimes(1);

      await act(async () => {
        resolveRequest({ data: [] });
      });
    }
  );
});