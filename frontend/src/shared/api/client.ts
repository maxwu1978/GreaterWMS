import axios from "axios";

import { useAuthStore } from "../hooks/useAuth";

function normalizeBaseUrl(baseUrl: string | undefined) {
  if (!baseUrl) return "/api/v1";
  return baseUrl.replace(/\/+$/, "");
}

const api = axios.create({
  baseURL: normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL),
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("wms_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clear stale auth state (token, role, permissions) before redirecting.
      useAuthStore.getState().logout();
      // We're outside React here, so a full-page navigation is acceptable.
      // Guard against redirect loops when the 401 happens on the login page itself.
      if (window.location.pathname !== "/login") {
        window.location.assign("/login");
      }
    }
    return Promise.reject(error);
  }
);

export default api;
