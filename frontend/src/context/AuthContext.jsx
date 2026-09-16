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


  const loadCurrentUser = async () => {
    const accessToken = localStorage.getItem(
      "access_token"
    );

    if (!accessToken) {
      setUser(null);
      setLoading(false);
      return;
    }

    try {
      const response = await api.get(
        "/accounts/me/"
      );

      setUser(response.data);
    } catch {
      setUser(null);

      localStorage.removeItem(
        "access_token"
      );

      localStorage.removeItem(
        "refresh_token"
      );
    } finally {
      setLoading(false);
    }
  };


  useEffect(() => {
    loadCurrentUser();
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
    username,
    password
  ) => {
    const tokenResponse = await api.post(
      "/accounts/login/",
      {
        username,
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