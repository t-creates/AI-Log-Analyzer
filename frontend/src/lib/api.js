const DEFAULT_BASE_URL = "http://127.0.0.1:8000";
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL;

async function request(path, { method = "GET", body, headers } = {}) {
  const url = `${API_BASE_URL}${path}`;

  const res = await fetch(url, {
    method,
    headers: { ...(headers || {}) },
    body,
  });

  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }

  if (!res.ok) {
    const msg =
      (data && (data.detail || data.error || data.message)) ||
      `Request failed (${res.status})`;
    const err = new Error(msg);
    err.status = res.status;
    err.data = data;
    throw err;
  }

  return data;
}

function json(path, { method = "GET", obj } = {}) {
  return request(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: obj ? JSON.stringify(obj) : undefined,
  });
}

export function uploadLogFile(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/upload", { method: "POST", body: form });
}

export function postQuery(question) {
  return json("/query", { method: "POST", obj: { question } });
}

export function getSummary() {
  return json("/summary");
}

export function getLogs(params = {}) {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && String(v).trim() !== "") usp.set(k, String(v));
  }
  const qs = usp.toString() ? `?${usp.toString()}` : "";
  return json(`/logs${qs}`);
}
