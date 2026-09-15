import { detailText } from "./copy.js";

const API = "/api";

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(detailText(data.detail) || response.statusText);
    error.status = response.status;
    error.payload = data;
    throw error;
  }
  return data;
}

export const api = {
  health: () => request("/health"),
  features: () => request("/features"),
  me: () => request("/auth/me"),
  login: (username, password) =>
    request("/auth/local/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => request("/auth/logout", { method: "POST" }),
  validateInvite: (token) => request(`/invites/validate?token=${encodeURIComponent(token)}`),
  redeem: (token, username, password) =>
    request("/invites/redeem/local", { method: "POST", body: JSON.stringify({ token, username, password }) }),
  mintInvite: (role) => request("/invites", { method: "POST", body: JSON.stringify({ role }) }),
  hall: () => request("/hall"),
  search: (q, { beyond = false, kind = "" } = {}) =>
    request(`/search?q=${encodeURIComponent(q)}&beyond=${beyond ? 1 : 0}&kind=${encodeURIComponent(kind)}`),
  work: (id) => request(`/works/${id}`),
  favorite: (id) => request(`/works/${id}/favorite`, { method: "POST" }),
  requestItem: (item) => request("/request", { method: "POST", body: JSON.stringify(item) }),
  review: () => request("/review"),
  reviewApply: (id, body) => request(`/review/${id}/apply`, { method: "POST", body: JSON.stringify(body) }),
  reviewSkip: (id) => request(`/review/${id}/skip`, { method: "POST" }),
  queue: () => request("/queue"),
  confirmJob: (id) => request(`/queue/${id}/confirm`, { method: "POST" }),
  gaps: () => request("/gaps"),
  confirmGap: (item) => request("/gaps/confirm", { method: "POST", body: JSON.stringify(item) }),
  settings: () => request("/settings"),
  saveSettings: (body) => request("/settings", { method: "PUT", body: JSON.stringify(body) }),
  people: () => request("/people"),
  promote: (id) => request(`/music/${id}/promote`, { method: "POST" }),
  pingIndexer: () => request("/indexers/ping", { method: "POST" }),
  indexers: () => request("/indexers"),
  progress: (id, body = {}) => request(`/works/${id}/progress`, { method: "POST", body: JSON.stringify(body) }),
  convert: (id, format) => request(`/works/${id}/convert`, { method: "POST", body: JSON.stringify({ format }) }),
};
