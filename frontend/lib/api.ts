import Constants from "expo-constants";

import type { PalettePreset, RenderConfig, RenderProject, RetroGameCard } from "./types";

const expoExtra = Constants.expoConfig?.extra as Record<string, string> | undefined;
const configuredUrl =
  expoExtra?.EXPO_PUBLIC_BACKEND_URL || process.env.EXPO_PUBLIC_BACKEND_URL || "";

export const API_BASE = `${configuredUrl.replace(/\/$/, "")}/api`;

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  if (!configuredUrl) {
    throw new Error("Backend URL is not configured");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function getPalettes() {
  return request<PalettePreset[]>("/palettes");
}

export function getGallery() {
  return request<RetroGameCard[]>("/gallery");
}

export function getRenderProjects() {
  return request<RenderProject[]>("/renders");
}

export function createRenderProject(input: {
  url: string;
  palette_id: string;
  config: RenderConfig;
  title?: string;
}) {
  return request<RenderProject>("/renders", {
    method: "POST",
    body: JSON.stringify(input),
  });
}