export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, token: string | null, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init, credentials: "include",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers },
  });
  if (!res.ok) {
    const d = await res.json().catch(() => null);
    throw new ApiError(res.status, typeof d?.detail === "string" ? d.detail : `The server answered with status ${res.status}.`);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}
