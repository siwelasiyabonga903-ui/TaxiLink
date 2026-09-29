// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import {
  MemoryRouter,
  Route,
  Routes,
} from "react-router-dom";

import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import api from "../api/client";
import LoginPage from "./LoginPage";


const authMocks = vi.hoisted(() => ({
  login: vi.fn(),
}));


vi.mock("../api/client", () => ({
  default: {
    post: vi.fn(),
  },
}));


vi.mock(
  "../context/AuthContext",
  () => ({
    useAuth: () => ({
      user: null,
      login: authMocks.login,
    }),
  })
);


function renderLogin(
  initialEntry = "/login"
) {
  return render(
    <MemoryRouter
      initialEntries={[initialEntry]}
    >
      <Routes>
        <Route
          path="/login"
          element={<LoginPage />}
        />

        <Route
          path="/dashboard"
          element={
            <div>Dashboard loaded</div>
          }
        />
      </Routes>
    </MemoryRouter>
  );
}


describe(
  "LoginPage email verification",
  () => {
    beforeEach(() => {
      vi.clearAllMocks();

      api.post.mockResolvedValue({
        data: {
          detail: (
            "If an unverified account exists, "
            + "a confirmation link has been sent."
          ),
        },
      });
    });

    afterEach(() => {
      cleanup();
    });


    it(
      "shows successful email verification",
      () => {
        renderLogin(
          "/login?verification=success"
        );

        expect(
          screen.getByText(
            /Email confirmed successfully/i
          )
        ).toBeInTheDocument();
      }
    );


    it(
      "shows an invalid verification link",
      () => {
        renderLogin(
          "/login?verification=invalid"
        );

        expect(
          screen.getByText(
            /confirmation link is invalid/i
          )
        ).toBeInTheDocument();
      }
    );


    it(
      "shows resend controls when unverified login is blocked",
      async () => {
        authMocks.login.mockRejectedValue({
          response: {
            data: {
              detail: (
                "Confirm your email before "
                + "signing in."
              ),
            },
          },
        });

        renderLogin();

        fireEvent.change(
          screen.getByPlaceholderText(
            "Username"
          ),
          {
            target: {
              value: "passenger1",
            },
          }
        );

        fireEvent.change(
          screen.getByPlaceholderText(
            "Password"
          ),
          {
            target: {
              value: "StrongPass123!",
            },
          }
        );

        fireEvent.click(
          screen.getByRole(
            "button",
            { name: "Login" }
          )
        );

        expect(
          await screen.findByText(
            /Confirm your email/i
          )
        ).toBeInTheDocument();

        expect(
          screen.getByLabelText(
            "Registration email"
          )
        ).toBeInTheDocument();
      }
    );


    it(
      "resends confirmation to a normalized email",
      async () => {
        renderLogin();

        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name: (
                "Resend confirmation email"
              ),
            }
          )
        );

        fireEvent.change(
          screen.getByLabelText(
            "Registration email"
          ),
          {
            target: {
              value: (
                "  Passenger@Example.COM  "
              ),
            },
          }
        );

        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name: (
                "Send confirmation link"
              ),
            }
          )
        );

        await waitFor(() => {
          expect(
            api.post
          ).toHaveBeenCalledWith(
            (
              "/accounts/"
              + "verify-email/resend/"
            ),
            {
              email:
                "passenger@example.com",
            }
          );
        });

        expect(
          await screen.findByText(
            /confirmation link has been sent/i
          )
        ).toBeInTheDocument();
      }
    );


    it(
      "prefills the registration email",
      () => {
        renderLogin({
          pathname: "/login",
          state: {
            message: (
              "Registration successful. "
              + "Check your email."
            ),
            verificationEmail:
              "passenger@example.com",
          },
        });

        expect(
          screen.getByText(
            /Registration successful/i
          )
        ).toBeInTheDocument();

        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name: (
                "Resend confirmation email"
              ),
            }
          )
        );

        expect(
          screen.getByLabelText(
            "Registration email"
          )
        ).toHaveValue(
          "passenger@example.com"
        );
      }
    );


    it(
      "trims username but preserves password spaces",
      async () => {
        authMocks.login.mockResolvedValue(
          {}
        );

        renderLogin();

        fireEvent.change(
          screen.getByPlaceholderText(
            "Username"
          ),
          {
            target: {
              value: "  passenger1  ",
            },
          }
        );

        fireEvent.change(
          screen.getByPlaceholderText(
            "Password"
          ),
          {
            target: {
              value: " Keep Spaces!1 ",
            },
          }
        );

        fireEvent.click(
          screen.getByRole(
            "button",
            { name: "Login" }
          )
        );

        await waitFor(() => {
          expect(
            authMocks.login
          ).toHaveBeenCalledWith(
            "passenger1",
            " Keep Spaces!1 "
          );
        });

        expect(
          await screen.findByText(
            "Dashboard loaded"
          )
        ).toBeInTheDocument();
      }
    );
  }
);