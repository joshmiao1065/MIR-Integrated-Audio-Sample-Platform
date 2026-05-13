import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const api = axios.create({
  baseURL: `${BASE_URL}/api`,
});

// Attach JWT token from localStorage to every request when present
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On 401, clear stored token so the user is effectively logged out
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("access_token");
    }
    return Promise.reject(err);
  }
);

/**
 * Returns a fresh axios instance for search requests.
 * Reads `search_api_url` from localStorage at call time so the URL can be
 * changed in the browser console without a page rebuild:
 *   localStorage.setItem("search_api_url", "https://xxxx.ngrok-free.app")
 * Omit or clear the key to fall back to the default Railway backend.
 */
export function createSearchApi() {
  const override = localStorage.getItem("search_api_url");
  const base = override ?? BASE_URL;
  const instance = axios.create({ baseURL: `${base}/api` });
  const token = localStorage.getItem("access_token");
  if (token) instance.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  return instance;
}
