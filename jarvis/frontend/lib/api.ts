export interface ChatResponse {
  reply: string;
  model_used: string;
  session_id: string;
}

export class JarvisApiError extends Error {}

function getConnection(): { baseUrl: string; token: string } {
  const baseUrl =
    (typeof window !== "undefined" && localStorage.getItem("jarvis_server_url")) ||
    process.env.NEXT_PUBLIC_JARVIS_API_URL ||
    "";
  const token =
    (typeof window !== "undefined" && localStorage.getItem("jarvis_api_token")) || "";
  return { baseUrl: baseUrl.replace(/\/$/, ""), token };
}

export function hasConnection(): boolean {
  const { baseUrl, token } = getConnection();
  return Boolean(baseUrl && token);
}

export function saveConnection(baseUrl: string, token: string): void {
  localStorage.setItem("jarvis_server_url", baseUrl.trim());
  localStorage.setItem("jarvis_api_token", token.trim());
}

export function getStoredConnection(): { baseUrl: string; token: string } {
  return getConnection();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { baseUrl, token } = getConnection();
  if (!baseUrl || !token) {
    throw new JarvisApiError("Nicht mit einem Jarvis-Server verbunden.");
  }

  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.headers || {}),
    },
  });

  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const body = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const detail = typeof body === "string" ? body : body?.detail || JSON.stringify(body);
    throw new JarvisApiError(detail);
  }
  return body as T;
}

export async function sendChatMessage(message: string, sessionId?: string): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
}

export async function checkHealth(baseUrl: string): Promise<boolean> {
  try {
    const res = await fetch(`${baseUrl.replace(/\/$/, "")}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

export async function speakText(text: string): Promise<Blob> {
  const { baseUrl, token } = getConnection();
  if (!baseUrl || !token) throw new JarvisApiError("Nicht verbunden.");

  const response = await fetch(`${baseUrl}/voice/speak`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new JarvisApiError(detail);
  }
  return response.blob();
}

export async function transcribeAudio(blob: Blob): Promise<string> {
  const { baseUrl, token } = getConnection();
  if (!baseUrl || !token) throw new JarvisApiError("Nicht verbunden.");

  const formData = new FormData();
  formData.append("audio", blob, "voice.webm");

  const response = await fetch(`${baseUrl}/voice/transcribe`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  const body = await response.json();
  if (!response.ok) throw new JarvisApiError(body?.detail || "Transkription fehlgeschlagen.");
  return body.text as string;
}
