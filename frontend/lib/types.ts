export type StripeMode = "horizontal" | "vertical" | "diagonal" | "grid";

export type RenderConfig = {
  stripe_mode: StripeMode;
  density: number;
  thickness: number;
  opacity: number;
  hex_enabled: boolean;
  animation_speed: number;
};

export type PalettePreset = {
  id: string;
  name: string;
  description: string;
  anchor: string;
  complement: string;
  colors: string[];
  mood: string;
};

export type RetroGameCard = {
  id: string;
  title: string;
  genre: string;
  description: string;
  colors: string[];
  geometry: string;
  intensity: number;
};

export type RenderProject = {
  id: string;
  title: string;
  url: string;
  host: string;
  palette_id: string;
  config: RenderConfig;
  signature: string;
  created_at: string;
};

export type TabKey = "render" | "gallery" | "palettes" | "saves";