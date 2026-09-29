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
            <div>
              Dashboard loaded
            </div>
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
      "automatically resends confirmation after a blocked login",
      async () => {
        authMocks.login.mockRejectedValue({
          response: {
            status: 401,

            data: {
              detail: (
                "Confirm your email address "
                + "before logging in."
              ),
            },
          },
        });

        renderLogin();

        fireEvent.change(
          screen.getByPlaceholderText(
            "Email address"
          ),
          {
            target: {
              value:
                "Passenger@Example.COM",
            },
          }
        );

        fireEvent.change(
          screen.getByPlaceholderText(
            "Password"
          ),
          {
            target: {
              value:
                "StrongPass123!",
            },
          }
        );

        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name: "Login",
            }
          )
        );

        await waitFor(() => {
          expect(
            authMocks.login
          ).toHaveBeenCalledWith(
            "passenger@example.com",
            "StrongPass123!"
          );
        });

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
            /fresh confirmation link has been sent/i
          )
        ).toBeInTheDocument();

        expect(
          screen.queryByRole(
            "button",
            {
              name:
                /Resend confirmation email/i,
            }
          )
        ).not.toBeInTheDocument();
      }
    );


    it(
      "shows an email or password error for invalid credentials",
      async () => {
        authMocks.login.mockRejectedValue({
          response: {
            status: 401,

            data: {
              detail:
                "No active account found.",
            },
          },
        });

        renderLogin();

        fireEvent.change(
          screen.getByPlaceholderText(
            "Email address"
          ),
          {
            target: {
              value:
                "passenger@example.com",
            },
          }
        );

        fireEvent.change(
          screen.getByPlaceholderText(
            "Password"
          ),
          {
            target: {
              value:
                "WrongPassword123!",
            },
          }
        );

        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name: "Login",
            }
          )
        );

        expect(
          await screen.findByText(
            "Email or password is incorrect."
          )
        ).toBeInTheDocument();

        expect(
          api.post
        ).not.toHaveBeenCalled();
      }
    );


    it(
      "shows registration success without resend controls",
      () => {
        renderLogin({
          pathname: "/login",

          state: {
            message: (
              "Registration successful. "
              + "Check your email."
            ),
          },
        });

        expect(
          screen.getByText(
            /Registration successful/i
          )
        ).toBeInTheDocument();

        expect(
          screen.queryByRole(
            "button",
            {
              name:
                /Resend confirmation email/i,
            }
          )
        ).not.toBeInTheDocument();

        expect(
          screen.queryByLabelText(
            "Registration email"
          )
        ).not.toBeInTheDocument();
      }
    );


    it(
      "normalizes email but preserves password spaces",
      async () => {
        authMocks.login.mockResolvedValue(
          {}
        );

        renderLogin();

        fireEvent.change(
          screen.getByPlaceholderText(
            "Email address"
          ),
          {
            target: {
              value:
                "Passenger@Example.COM",
            },
          }
        );

        fireEvent.change(
          screen.getByPlaceholderText(
            "Password"
          ),
          {
            target: {
              value:
                " Keep Spaces!1 ",
            },
          }
        );

        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name: "Login",
            }
          )
        );

        await waitFor(() => {
          expect(
            authMocks.login
          ).toHaveBeenCalledWith(
            "passenger@example.com",
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