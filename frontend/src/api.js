const BASE = "/api";

// The session is an httpOnly cookie managed by the server; JS never sees it.
// The CSRF token lives in a readable cookie and is echoed on every mutation.
function csrfToken() {
  const m = document.cookie.match(/(?:^|;\s*)hr_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function req(path, opts = {}) {
  const method = (opts.method || "GET").toUpperCase();
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (method !== "GET" && method !== "HEAD") headers["X-CSRF-Token"] = csrfToken();

  const res = await fetch(BASE + path, { credentials: "same-origin", ...opts, headers });
  if (res.status === 401) {
    window.dispatchEvent(new Event("hr-logout"));
    throw Object.assign(new Error("Unauthorized"), { status: 401 });
  }
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      detail = "";
    }
    throw Object.assign(new Error(detail || `Request failed (${res.status})`), { status: res.status });
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  login: (email, password, rememberMe = false) =>
    req("/auth/login", { method: "POST", body: JSON.stringify({ email, password, remember_me: rememberMe }) }),
  logout: () => req("/auth/logout", { method: "POST" }).catch(() => null),
  me: () => req("/auth/me"),
  forgotPassword: (email) => req("/auth/forgot", { method: "POST", body: JSON.stringify({ email }) }),
  resetPassword: (token, newPassword) =>
    req("/auth/reset", { method: "POST", body: JSON.stringify({ token, new_password: newPassword }) }),

  listUsers: () => req("/auth/users"),
  createUser: (data) => req("/auth/users", { method: "POST", body: JSON.stringify(data) }),
  deactivateUser: (id) => req(`/auth/users/${id}`, { method: "DELETE" }),

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

  getSettings: () => req("/settings"),
  sendTestEmail: (to) => req("/settings/test-email", { method: "POST", body: JSON.stringify({ to: to || null }) }),

  exportViolations: async (filters = {}) => {
    const qs = new URLSearchParams(
      Object.entries(filters).filter(([, v]) => v !== undefined && v !== null && v !== "")
    ).toString();
    const res = await fetch(`${BASE}/violations/export${qs ? `?${qs}` : ""}`, { credentials: "same-origin" });
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
