const BASE = "/api";
const AUTH_KEY = "hr_auth";

// sessionStorage (not localStorage): credentials are cleared when the tab
// closes and aren't shared across tabs. Interim measure until the Phase 2
// auth module replaces Basic auth with httpOnly cookie sessions.
export const auth = {
  get: () => sessionStorage.getItem(AUTH_KEY),
  set: (username, password) => {
    sessionStorage.setItem(AUTH_KEY, btoa(`${username}:${password}`));
  },
  clear: () => sessionStorage.removeItem(AUTH_KEY),
};

async function req(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  const token = auth.get();
  if (token) headers.Authorization = `Basic ${token}`;

  const res = await fetch(BASE + path, { ...opts, headers });
  if (res.status === 401) {
    auth.clear();
    window.dispatchEvent(new Event("hr-logout"));
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  login: (username, password) => {
    const token = btoa(`${username}:${password}`);
    return fetch(`${BASE}/auth/check`, {
      headers: { Authorization: `Basic ${token}` },
    }).then((r) => {
      if (!r.ok) throw new Error("Invalid credentials");
      auth.set(username, password);
      return r.json();
    });
  },
  logout: () => auth.clear(),

  listEmployees: () => req("/employees"),
  createEmployee: (data) => req("/employees", { method: "POST", body: JSON.stringify(data) }),
  deleteEmployee: (name) => req(`/employees/${encodeURIComponent(name)}`, { method: "DELETE" }),

  listViolations: (filters = {}) => {
    const qs = new URLSearchParams(
      Object.entries(filters).filter(([, v]) => v !== undefined && v !== null && v !== "")
    ).toString();
    return req(`/violations${qs ? `?${qs}` : ""}`);
  },
  createViolation: (data) => req("/violations", { method: "POST", body: JSON.stringify(data) }),
  deleteViolation: (id) => req(`/violations/${id}`, { method: "DELETE" }),
  previewPenalty: (employee_name, category, incident) => {
    const qs = new URLSearchParams({ employee_name, category, incident }).toString();
    return req(`/violations/preview?${qs}`);
  },

  dashboard: () => req("/stats/dashboard"),
  matrix: () => req("/matrix"),

  exportViolations: async (filters = {}) => {
    const qs = new URLSearchParams(
      Object.entries(filters).filter(([, v]) => v !== undefined && v !== null && v !== "")
    ).toString();
    const token = auth.get();
    const res = await fetch(`${BASE}/violations/export${qs ? `?${qs}` : ""}`, {
      headers: token ? { Authorization: `Basic ${token}` } : {},
    });
    if (!res.ok) throw new Error(`${res.status}: export failed`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `violations_${new Date().toISOString().slice(0, 10)}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};
