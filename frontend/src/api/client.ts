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

// Build-time search backend override (set VITE_SEARCH_URL in Vercel env settings).
// Falls back to the main API URL if not set.
const SEARCH_BASE_URL = import.meta.env.VITE_SEARCH_URL ?? BASE_URL;

/**
 * Returns a fresh axios instance for search requests.
 * Priority (highest first):
 *   1. localStorage "search_api_url"  — per-browser runtime override (browser console)
 *   2. VITE_SEARCH_URL env var        — baked at build time via Vercel env settings
 *   3. VITE_API_URL / localhost        — default Railway backend
 */
export function createSearchApi() {
  const override = localStorage.getItem("search_api_url");
  const base = override ?? SEARCH_BASE_URL;
  const instance = axios.create({
    baseURL: `${base}/api`,
    // ngrok free tier shows a browser-warning interstitial; this header bypasses it.
    // Ignored by Railway and any non-ngrok backend.
    headers: { "ngrok-skip-browser-warning": "1" },
  });
  const token = localStorage.getItem("access_token");
  if (token) instance.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  return instance;
}
