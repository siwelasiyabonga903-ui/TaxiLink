import {
  createContext,
  useContext,
  useEffect,
  useState,
} from "react";

import api from "../api/client";


const AuthContext = createContext(null);


export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);


  useEffect(() => {
    let cancelled = false;
    let retryTimer = null;

    const retry = (delay) => {
      if (cancelled) {
        return;
      }

      retryTimer = window.setTimeout(() => {
        retryTimer = null;
        loadCurrentUser();
      }, delay);
    };

    const loadCurrentUser = async () => {
      const accessToken =
        localStorage.getItem("access_token");

      const refreshToken =
        localStorage.getItem("refresh_token");

      if (!accessToken) {
        if (!cancelled) {
          setUser(null);
          setLoading(false);
        }

        return;
      }

      try {
        const response = await api.get(
          "/accounts/me/",
          { timeout: 15000 }
        );

        if (cancelled) {
          return;
        }

        if (
          localStorage.getItem("refresh_token")
          !== refreshToken
        ) {
          retry(0);
          return;
        }

        if (!localStorage.getItem("access_token")) {
          setUser(null);
          setLoading(false);
          return;
        }

        setUser(response.data);
        setLoading(false);
      } catch (error) {
        if (cancelled) {
          return;
        }

        const currentAccess =
          localStorage.getItem("access_token");

        const currentRefresh =
          localStorage.getItem("refresh_token");

        // A different login or a successful refresh changed
        // the tokens while this request was in flight.
        if (
          currentRefresh !== refreshToken ||
          (currentAccess && currentAccess !== accessToken)
        ) {
          retry(0);
          return;
        }

        if (
          [401, 403].includes(error?.response?.status) ||
          !currentAccess
        ) {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          setUser(null);
          setLoading(false);
          return;
        }

        // Keep loading the session and retry after a
        // temporary network or server failure.
        retry(5000);
      }
    };

    loadCurrentUser();

    return () => {
      cancelled = true;

      if (retryTimer !== null) {
        window.clearTimeout(retryTimer);
      }
    };
  }, []);


  const registerPassenger = async (
    formData
  ) => {
    return api.post(
      "/accounts/register/",
      formData
    );
  };


  const login = async (
  email,
  password
) => {
  const normalizedEmail =
    email.trim().toLowerCase();

  const tokenResponse = await api.post(
    "/accounts/login/",
    {
      // Django still uses this internal key.
      username: normalizedEmail,
      password,
    }
  );

  localStorage.setItem(
    "access_token",
    tokenResponse.data.access
  );

  localStorage.setItem(
    "refresh_token",
    tokenResponse.data.refresh
  );

  const profileResponse = await api.get(
    "/accounts/me/"
  );

  setUser(profileResponse.data);

  return profileResponse.data;
};


  const changeDriverPassword = async (
    formData
  ) => {
    const response = await api.post(
      "/accounts/drivers/change-password/",
      formData
    );

    const profileResponse = await api.get(
      "/accounts/me/"
    );

    setUser(profileResponse.data);

    return response.data;
  };


  const changeAccountPassword = async (
    formData
  ) => {
    const response = await api.post(
      "/accounts/change-password/",
      formData
    );

    return response.data;
  };


  const updateProfile = async (
    formData
  ) => {
    const response = await api.patch(
      "/accounts/me/",
      formData
    );

    setUser(response.data);

    return response.data;
  };


  const logout = async () => {
    const refreshToken =
      localStorage.getItem(
        "refresh_token"
      );

    try {
      if (refreshToken) {
        await api.post(
          "/accounts/logout/",
          {
            refresh: refreshToken,
          }
        );
      }
    } finally {
      localStorage.removeItem(
        "access_token"
      );

      localStorage.removeItem(
        "refresh_token"
      );

      setUser(null);
    }
  };


  const value = {
    user,
    loading,
    login,
    logout,
    registerPassenger,
    changeDriverPassword,
    changeAccountPassword,
    updateProfile,
  };


  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}


export function useAuth() {
  const context = useContext(
    AuthContext
  );

  if (!context) {
    throw new Error(
      "useAuth must be used inside AuthProvider."
    );
  }

  return context;
}