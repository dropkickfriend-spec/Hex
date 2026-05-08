import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useFonts } from "expo-font";
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { RenderCanvas } from "../components/RenderCanvas";
import {
  createRenderProject,
  getGallery,
  getPalettes,
  getRenderProjects,
} from "../lib/api";
import type {
  PalettePreset,
  RenderConfig,
  RenderProject,
  RetroGameCard,
  StripeMode,
  TabKey,
} from "../lib/types";

const INITIAL_CONFIG: RenderConfig = {
  stripe_mode: "diagonal",
  density: 10,
  thickness: 5,
  opacity: 82,
  hex_enabled: true,
  animation_speed: 4,
};

const STRIPE_MODES: { label: string; value: StripeMode; icon: keyof typeof MaterialCommunityIcons.glyphMap }[] = [
  { label: "Horizontal", value: "horizontal", icon: "format-align-justify" },
  { label: "Vertical", value: "vertical", icon: "view-headline" },
  { label: "Diagonal", value: "diagonal", icon: "slash-forward" },
  { label: "Grid", value: "grid", icon: "grid" },
];

function withProtocol(url: string) {
  const clean = url.trim();
  if (!clean) return "";
  return /^https?:\/\//i.test(clean) ? clean : `https://${clean}`;
}

function Button({
  title,
  icon,
  onPress,
  active,
  disabled,
  testID,
}: {
  title: string;
  icon?: keyof typeof MaterialCommunityIcons.glyphMap;
  onPress: () => void;
  active?: boolean;
  disabled?: boolean;
  testID?: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      testID={testID}
      style={({ pressed }) => [
        styles.button,
        active && styles.buttonActive,
        disabled && styles.buttonDisabled,
        pressed && !disabled && styles.buttonPressed,
      ]}
    >
      {icon ? <MaterialCommunityIcons name={icon} size={17} color={active ? "#050505" : "#00FFFF"} /> : null}
      <Text style={[styles.buttonText, active && styles.buttonTextActive]}>{title}</Text>
    </Pressable>
  );
}

function Stepper({
  label,
  value,
  min,
  max,
  step,
  suffix,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  suffix?: string;
  onChange: (value: number) => void;
}) {
  const percent = ((value - min) / (max - min)) * 100;
  return (
    <View style={styles.stepper}>
      <View style={styles.rowBetween}>
        <Text style={styles.controlLabel}>{label}</Text>
        <Text style={styles.controlValue}>{value}{suffix || ""}</Text>
      </View>
      <View style={styles.stepperRow}>
        <Pressable
          accessibilityRole="button"
          onPress={() => onChange(Math.max(min, value - step))}
          style={styles.stepperButton}
        >
          <Text style={styles.stepperText}>−</Text>
        </Pressable>
        <View style={styles.track}>
          <View style={[styles.trackFill, { width: `${percent}%` }]} />
        </View>
        <Pressable
          accessibilityRole="button"
          onPress={() => onChange(Math.min(max, value + step))}
          style={styles.stepperButton}
        >
          <Text style={styles.stepperText}>+</Text>
        </Pressable>
      </View>
    </View>
  );
}

function Header({ activeTab }: { activeTab: TabKey }) {
  const title = activeTab === "render" ? "MunkerHex Studio" : activeTab === "gallery" ? "Retro Redesigns" : activeTab === "palettes" ? "CMY Palette Grid" : "Saved Renders";
  return (
    <View style={styles.header}>
      <View style={styles.logoMark}>
        <View style={styles.logoCubeOne} />
        <View style={styles.logoCubeTwo} />
      </View>
      <View style={styles.headerTextBlock}>
        <Text style={styles.headerKicker}>ANIMATED MUNKER RENDER</Text>
        <Text style={styles.headerTitle}>{title}</Text>
      </View>
    </View>
  );
}

function RenderStudio({
  url,
  setUrl,
  palettes,
  selectedPalette,
  selectedPaletteId,
  setSelectedPaletteId,
  config,
  setConfig,
  latestProject,
  onRender,
  isRendering,
  error,
}: {
  url: string;
  setUrl: (value: string) => void;
  palettes: PalettePreset[];
  selectedPalette?: PalettePreset;
  selectedPaletteId: string;
  setSelectedPaletteId: (value: string) => void;
  config: RenderConfig;
  setConfig: (value: RenderConfig) => void;
  latestProject?: RenderProject | null;
  onRender: () => void;
  isRendering: boolean;
  error?: string | null;
}) {
  const updateConfig = (patch: Partial<RenderConfig>) => setConfig({ ...config, ...patch });

  return (
    <ScrollView
      keyboardShouldPersistTaps="handled"
      showsVerticalScrollIndicator={false}
      contentContainerStyle={styles.screenContent}
    >
      <View style={styles.introPanel}>
        <Text style={styles.kicker}>URL → LOCAL STYLE FIELD</Text>
        <Text style={styles.heroTitle}>Render a website address as an animated CMY hex illusion.</Text>
        <Text style={styles.bodyText}>
          This MVP turns the URL into a deterministic visual preview, then layers Munker stripes, hex cells and additive complements over the composition.
        </Text>
      </View>

      <View style={styles.urlPanel}>
        <Text style={styles.controlLabel}>Website URL</Text>
        <View style={styles.inputRow}>
          <TextInput
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            onChangeText={setUrl}
            onSubmitEditing={() => {
              Keyboard.dismiss();
              onRender();
            }}
            placeholder="example.com"
            placeholderTextColor="#5C5C66"
            returnKeyType="go"
            style={styles.input}
            testID="url-preview-input"
            value={url}
          />
          <Button
            disabled={isRendering || !url.trim()}
            icon="auto-fix"
            onPress={onRender}
            testID="render-preview-button"
            title={isRendering ? "Rendering" : "Render"}
          />
        </View>
        {error ? <Text style={styles.errorText}>{error}</Text> : null}
      </View>

      <RenderCanvas
        config={config}
        isRendering={isRendering}
        latestProject={latestProject}
        palette={selectedPalette}
        url={url}
      />

      <View style={styles.controlSheet}>
        <View style={styles.rowBetween}>
          <View>
            <Text style={styles.sheetTitle}>Munker filter</Text>
            <Text style={styles.bodyText}>Animated line overlay + hex-grid optical field</Text>
          </View>
          <Button
            active={config.opacity > 10}
            icon="blur-linear"
            onPress={() => updateConfig({ opacity: config.opacity > 10 ? 10 : 82 })}
            testID="munker-effect-toggle"
            title={config.opacity > 10 ? "On" : "Off"}
          />
        </View>

        <View style={styles.modeGrid}>
          {STRIPE_MODES.map((mode) => (
            <Button
              active={config.stripe_mode === mode.value}
              icon={mode.icon}
              key={mode.value}
              onPress={() => updateConfig({ stripe_mode: mode.value })}
              title={mode.label}
            />
          ))}
        </View>

        <View style={styles.paletteStrip}>
          <Text style={styles.controlLabel}>Palette preset</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.paletteScroller}>
            {palettes.map((palette) => (
              <Pressable
                accessibilityRole="button"
                key={palette.id}
                onPress={() => setSelectedPaletteId(palette.id)}
                style={[styles.paletteChip, selectedPaletteId === palette.id && styles.paletteChipActive]}
              >
                <View style={styles.swatchStack}>
                  {palette.colors.slice(0, 4).map((color) => (
                    <View key={`${palette.id}-${color}`} style={[styles.swatchDot, { backgroundColor: color }]} />
                  ))}
                </View>
                <Text style={styles.paletteChipText}>{palette.name}</Text>
              </Pressable>
            ))}
          </ScrollView>
        </View>

        <View style={styles.controlGrid}>
          <Stepper label="Density" max={24} min={4} onChange={(density) => updateConfig({ density })} step={2} value={config.density} />
          <Stepper label="Thickness" max={12} min={1} onChange={(thickness) => updateConfig({ thickness })} step={1} value={config.thickness} />
          <Stepper label="Opacity" max={100} min={10} onChange={(opacity) => updateConfig({ opacity })} step={6} suffix="%" value={config.opacity} />
          <Stepper label="Speed" max={12} min={1} onChange={(animation_speed) => updateConfig({ animation_speed })} step={1} suffix="s" value={config.animation_speed} />
        </View>

        <Button
          active={config.hex_enabled}
          icon="hexagon-multiple"
          onPress={() => updateConfig({ hex_enabled: !config.hex_enabled })}
          title={config.hex_enabled ? "Hex grid enabled" : "Hex grid disabled"}
        />
      </View>
    </ScrollView>
  );
}

function GameVisual({ game }: { game: RetroGameCard }) {
  const cells = useMemo(() => Array.from({ length: 18 }, (_, index) => index), []);
  return (
    <View style={styles.gameVisual}>
      {cells.map((cell) => (
        <View
          key={`${game.id}-visual-${cell}`}
          style={[
            styles.gameCell,
            {
              backgroundColor: game.colors[cell % game.colors.length],
              height: game.genre.includes("Platformer") && cell > 10 ? 28 : 16 + (cell % 3) * 7,
              opacity: 0.35 + (cell % 4) * 0.16,
              transform: [{ rotate: game.genre.includes("Puzzle") ? "45deg" : "0deg" }],
            },
          ]}
        />
      ))}
    </View>
  );
}

function GalleryScreen({ games }: { games: RetroGameCard[] }) {
  return (
    <ScrollView
      contentContainerStyle={styles.screenContent}
      showsVerticalScrollIndicator={false}
      testID="retro-gallery-scrollview"
    >
      <View style={styles.introPanel}>
        <Text style={styles.kicker}>OLD-SCHOOL / NEW RENDER</Text>
        <Text style={styles.heroTitle}>Retro game concepts rebuilt with CMY light and hex rhythm.</Text>
      </View>
      {games.map((game) => (
        <Pressable key={game.id} testID="retro-game-card" style={({ pressed }) => [styles.gameCard, pressed && styles.buttonPressed]}>
          <GameVisual game={game} />
          <View style={styles.gameInfo}>
            <View style={styles.rowBetween}>
              <Text style={styles.gameGenre}>{game.genre}</Text>
              <Text style={styles.intensity}>{game.intensity}%</Text>
            </View>
            <Text style={styles.cardTitle}>{game.title}</Text>
            <Text style={styles.bodyText}>{game.description}</Text>
            <Text style={styles.geometryText}>{game.geometry}</Text>
          </View>
        </Pressable>
      ))}
    </ScrollView>
  );
}

function PaletteScreen({
  palettes,
  selectedPaletteId,
  setSelectedPaletteId,
}: {
  palettes: PalettePreset[];
  selectedPaletteId: string;
  setSelectedPaletteId: (value: string) => void;
}) {
  return (
    <ScrollView contentContainerStyle={styles.screenContent} showsVerticalScrollIndicator={false}>
      <View style={styles.introPanel}>
        <Text style={styles.kicker}>TONAL CENTRE / COMPLEMENT</Text>
        <Text style={styles.heroTitle}>Select the color logic behind the hex render.</Text>
      </View>
      {palettes.map((palette) => (
        <Pressable
          accessibilityRole="button"
          key={palette.id}
          onPress={() => setSelectedPaletteId(palette.id)}
          style={[styles.paletteCard, selectedPaletteId === palette.id && styles.paletteCardActive]}
        >
          <View style={styles.rowBetween}>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle}>{palette.name}</Text>
              <Text style={styles.bodyText}>{palette.description}</Text>
            </View>
            <MaterialCommunityIcons
              color={selectedPaletteId === palette.id ? "#FFFF00" : "#3F3F46"}
              name={selectedPaletteId === palette.id ? "radiobox-marked" : "radiobox-blank"}
              size={24}
            />
          </View>
          <View style={styles.hexPaletteRow}>
            {palette.colors.map((color, index) => (
              <View key={`${palette.id}-hex-${color}-${index}`} style={[styles.hexSwatch, { borderColor: color }]}> 
                <View style={[styles.hexSwatchInner, { backgroundColor: color }]} />
              </View>
            ))}
          </View>
          <View style={styles.paletteMetaRow}>
            <Text style={styles.metaText}>A {palette.anchor}</Text>
            <Text style={styles.metaText}>B {palette.complement}</Text>
            <Text style={styles.metaText}>{palette.mood}</Text>
          </View>
        </Pressable>
      ))}
    </ScrollView>
  );
}

function SavesScreen({
  projects,
  palettes,
  onLoadProject,
}: {
  projects: RenderProject[];
  palettes: PalettePreset[];
  onLoadProject: (project: RenderProject) => void;
}) {
  return (
    <ScrollView contentContainerStyle={styles.screenContent} showsVerticalScrollIndicator={false}>
      <View style={styles.introPanel}>
        <Text style={styles.kicker}>SAVED STYLE PASSES</Text>
        <Text style={styles.heroTitle}>Reopen any URL render and keep tuning it.</Text>
      </View>
      {projects.length === 0 ? (
        <View style={styles.emptyPanel}>
          <MaterialCommunityIcons color="#00FFFF" name="content-save-outline" size={34} />
          <Text style={styles.emptyTitle}>No saved renders yet</Text>
          <Text style={styles.bodyText}>Create one from the Render tab and it will appear here.</Text>
        </View>
      ) : null}
      {projects.map((project) => {
        const palette = palettes.find((item) => item.id === project.palette_id);
        return (
          <Pressable
            accessibilityRole="button"
            key={project.id}
            onPress={() => onLoadProject(project)}
            style={({ pressed }) => [styles.saveCard, pressed && styles.buttonPressed]}
          >
            <View style={styles.rowBetween}>
              <View style={{ flex: 1 }}>
                <Text style={styles.cardTitle}>{project.title}</Text>
                <Text style={styles.bodyText}>{project.url}</Text>
              </View>
              <Text style={styles.signatureBig}>{project.signature}</Text>
            </View>
            <View style={styles.saveFooter}>
              <Text style={styles.metaText}>{palette?.name || project.palette_id}</Text>
              <Text style={styles.metaText}>{project.config.stripe_mode} · {project.config.opacity}%</Text>
            </View>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

function TabBar({ activeTab, setActiveTab, bottomInset }: { activeTab: TabKey; setActiveTab: (tab: TabKey) => void; bottomInset: number }) {
  const tabs: { key: TabKey; label: string; icon: keyof typeof MaterialCommunityIcons.glyphMap }[] = [
    { key: "render", label: "Render", icon: "auto-fix" },
    { key: "gallery", label: "Gallery", icon: "gamepad-variant-outline" },
    { key: "palettes", label: "Palette", icon: "palette-outline" },
    { key: "saves", label: "Saves", icon: "content-save-outline" },
  ];

  return (
    <View style={[styles.tabBar, { paddingBottom: Math.max(bottomInset, 12) }]}> 
      {tabs.map((tab) => {
        const active = activeTab === tab.key;
        return (
          <Pressable
            accessibilityRole="tab"
            key={tab.key}
            onPress={() => setActiveTab(tab.key)}
            style={({ pressed }) => [styles.tabItem, active && styles.tabItemActive, pressed && styles.buttonPressed]}
          >
            <MaterialCommunityIcons color={active ? "#050505" : "#A1A1AA"} name={tab.icon} size={20} />
            <Text style={[styles.tabText, active && styles.tabTextActive]}>{tab.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export default function Index() {
  const insets = useSafeAreaInsets();
  const [fontsLoaded] = useFonts({ SpaceMono: require("../assets/fonts/SpaceMono-Regular.ttf") });
  const [activeTab, setActiveTab] = useState<TabKey>("render");
  const [url, setUrl] = useState("emergent.sh");
  const [palettes, setPalettes] = useState<PalettePreset[]>([]);
  const [games, setGames] = useState<RetroGameCard[]>([]);
  const [projects, setProjects] = useState<RenderProject[]>([]);
  const [selectedPaletteId, setSelectedPaletteId] = useState("cmy-inverse");
  const [config, setConfig] = useState<RenderConfig>(INITIAL_CONFIG);
  const [latestProject, setLatestProject] = useState<RenderProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [isRendering, setIsRendering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedPalette = useMemo(
    () => palettes.find((palette) => palette.id === selectedPaletteId) || palettes[0],
    [palettes, selectedPaletteId],
  );

  const loadData = useCallback(async (showRefresh = false) => {
    try {
      if (showRefresh) setRefreshing(true);
      setError(null);
      const [paletteData, galleryData, projectData] = await Promise.all([
        getPalettes(),
        getGallery(),
        getRenderProjects(),
      ]);
      setPalettes(paletteData);
      setGames(galleryData);
      setProjects(projectData);
      if (paletteData.length && !paletteData.some((item) => item.id === selectedPaletteId)) {
        setSelectedPaletteId(paletteData[0].id);
      }
      if (projectData[0]) setLatestProject(projectData[0]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not load studio data");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedPaletteId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRender = useCallback(async () => {
    const fullUrl = withProtocol(url);
    if (!fullUrl || !selectedPalette) {
      setError("Enter a website URL and choose a palette.");
      return;
    }
    try {
      Keyboard.dismiss();
      setError(null);
      setIsRendering(true);
      const project = await createRenderProject({
        url: fullUrl,
        palette_id: selectedPalette.id,
        config,
      });
      setUrl(fullUrl);
      setLatestProject(project);
      setProjects((current) => [project, ...current.filter((item) => item.id !== project.id)]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Render could not be saved");
    } finally {
      setIsRendering(false);
    }
  }, [config, selectedPalette, url]);

  const handleLoadProject = (project: RenderProject) => {
    setUrl(project.url);
    setConfig(project.config);
    setSelectedPaletteId(project.palette_id);
    setLatestProject(project);
    setActiveTab("render");
  };

  if (!fontsLoaded || loading) {
    return (
      <SafeAreaView style={styles.loadingScreen}>
        <StatusBar style="light" />
        <ActivityIndicator color="#00FFFF" size="large" />
        <Text style={styles.loadingText}>loading MunkerHex Studio…</Text>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea} edges={["top", "left", "right"]}>
      <StatusBar style="light" />
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        style={styles.keyboardView}
      >
        <Header activeTab={activeTab} />
        <View style={styles.contentFrame}>
          {activeTab === "render" ? (
            <RenderStudio
              config={config}
              error={error}
              isRendering={isRendering}
              latestProject={latestProject}
              onRender={handleRender}
              palettes={palettes}
              selectedPalette={selectedPalette}
              selectedPaletteId={selectedPaletteId}
              setConfig={setConfig}
              setSelectedPaletteId={setSelectedPaletteId}
              setUrl={setUrl}
              url={url}
            />
          ) : null}
          {activeTab === "gallery" ? <GalleryScreen games={games} /> : null}
          {activeTab === "palettes" ? (
            <PaletteScreen
              palettes={palettes}
              selectedPaletteId={selectedPaletteId}
              setSelectedPaletteId={setSelectedPaletteId}
            />
          ) : null}
          {activeTab === "saves" ? (
            <ScrollView
              refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadData(true)} tintColor="#00FFFF" />}
              style={styles.flex}
            >
              <SavesScreen onLoadProject={handleLoadProject} palettes={palettes} projects={projects} />
            </ScrollView>
          ) : null}
        </View>
        <TabBar activeTab={activeTab} bottomInset={insets.bottom} setActiveTab={setActiveTab} />
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    backgroundColor: "#050505",
    flex: 1,
  },
  keyboardView: {
    flex: 1,
  },
  flex: {
    flex: 1,
  },
  loadingScreen: {
    alignItems: "center",
    backgroundColor: "#050505",
    flex: 1,
    justifyContent: "center",
  },
  loadingText: {
    color: "#00FFFF",
    fontFamily: "SpaceMono",
    fontSize: 12,
    letterSpacing: 1,
    marginTop: 16,
  },
  header: {
    alignItems: "center",
    borderBottomColor: "rgba(255,255,255,0.12)",
    borderBottomWidth: 1,
    flexDirection: "row",
    paddingHorizontal: 18,
    paddingVertical: 14,
  },
  logoMark: {
    height: 40,
    marginRight: 12,
    width: 40,
  },
  logoCubeOne: {
    backgroundColor: "#00FFFF",
    height: 22,
    left: 4,
    position: "absolute",
    top: 8,
    transform: [{ rotate: "45deg" }],
    width: 22,
  },
  logoCubeTwo: {
    backgroundColor: "#FF00FF",
    height: 22,
    left: 15,
    opacity: 0.74,
    position: "absolute",
    top: 8,
    transform: [{ rotate: "45deg" }],
    width: 22,
  },
  headerTextBlock: {
    flex: 1,
  },
  headerKicker: {
    color: "#A1A1AA",
    fontFamily: "SpaceMono",
    fontSize: 9,
    letterSpacing: 1.6,
  },
  headerTitle: {
    color: "#FFFFFF",
    fontFamily: "SpaceMono",
    fontSize: 22,
    marginTop: 3,
  },
  contentFrame: {
    flex: 1,
  },
  screenContent: {
    paddingBottom: 26,
    paddingHorizontal: 16,
    paddingTop: 16,
  },
  introPanel: {
    backgroundColor: "#111111",
    borderColor: "rgba(255,255,255,0.12)",
    borderWidth: 1,
    marginBottom: 14,
    padding: 16,
  },
  kicker: {
    color: "#00FFFF",
    fontFamily: "SpaceMono",
    fontSize: 10,
    letterSpacing: 1.7,
    marginBottom: 8,
  },
  heroTitle: {
    color: "#FFFFFF",
    fontFamily: "SpaceMono",
    fontSize: 24,
    lineHeight: 31,
  },
  bodyText: {
    color: "#A1A1AA",
    fontFamily: "SpaceMono",
    fontSize: 12,
    lineHeight: 19,
    marginTop: 8,
  },
  urlPanel: {
    backgroundColor: "#050505",
    borderColor: "rgba(255,255,255,0.12)",
    borderWidth: 1,
    marginBottom: 14,
    padding: 14,
  },
  inputRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    marginTop: 9,
  },
  input: {
    borderColor: "rgba(255,255,255,0.18)",
    borderWidth: 1,
    color: "#FFFFFF",
    flex: 1,
    fontFamily: "SpaceMono",
    fontSize: 13,
    minHeight: 48,
    paddingHorizontal: 12,
  },
  errorText: {
    color: "#FF3131",
    fontFamily: "SpaceMono",
    fontSize: 11,
    lineHeight: 17,
    marginTop: 10,
  },
  button: {
    alignItems: "center",
    borderColor: "#00FFFF",
    borderWidth: 1,
    flexDirection: "row",
    gap: 6,
    justifyContent: "center",
    minHeight: 46,
    minWidth: 46,
    paddingHorizontal: 13,
  },
  buttonActive: {
    backgroundColor: "#00FFFF",
  },
  buttonDisabled: {
    borderColor: "rgba(255,255,255,0.14)",
    opacity: 0.45,
  },
  buttonPressed: {
    opacity: 0.72,
    transform: [{ scale: 0.98 }],
  },
  buttonText: {
    color: "#00FFFF",
    fontFamily: "SpaceMono",
    fontSize: 11,
  },
  buttonTextActive: {
    color: "#050505",
  },
  controlSheet: {
    backgroundColor: "rgba(5,5,5,0.96)",
    borderColor: "rgba(255,255,255,0.12)",
    borderWidth: 1,
    marginTop: 14,
    padding: 16,
  },
  rowBetween: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  sheetTitle: {
    color: "#FFFFFF",
    fontFamily: "SpaceMono",
    fontSize: 19,
  },
  controlLabel: {
    color: "#A1A1AA",
    fontFamily: "SpaceMono",
    fontSize: 10,
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },
  controlValue: {
    color: "#FFFF00",
    fontFamily: "SpaceMono",
    fontSize: 12,
  },
  modeGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 16,
  },
  paletteStrip: {
    marginTop: 18,
  },
  paletteScroller: {
    gap: 10,
    paddingTop: 10,
  },
  paletteChip: {
    borderColor: "rgba(255,255,255,0.12)",
    borderWidth: 1,
    minHeight: 70,
    padding: 10,
    width: 160,
  },
  paletteChipActive: {
    borderColor: "#FF00FF",
  },
  swatchStack: {
    flexDirection: "row",
    gap: 4,
    marginBottom: 8,
  },
  swatchDot: {
    height: 14,
    width: 22,
  },
  paletteChipText: {
    color: "#FFFFFF",
    fontFamily: "SpaceMono",
    fontSize: 11,
  },
  controlGrid: {
    gap: 14,
    marginTop: 16,
  },
  stepper: {
    gap: 8,
  },
  stepperRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
  },
  stepperButton: {
    alignItems: "center",
    borderColor: "rgba(255,255,255,0.18)",
    borderWidth: 1,
    height: 44,
    justifyContent: "center",
    width: 44,
  },
  stepperText: {
    color: "#FFFFFF",
    fontFamily: "SpaceMono",
    fontSize: 22,
  },
  track: {
    backgroundColor: "rgba(255,255,255,0.10)",
    flex: 1,
    height: 10,
    overflow: "hidden",
  },
  trackFill: {
    backgroundColor: "#FF00FF",
    height: "100%",
  },
  gameCard: {
    backgroundColor: "#050505",
    borderColor: "rgba(255,255,255,0.12)",
    borderWidth: 1,
    marginBottom: 14,
    overflow: "hidden",
  },
  gameVisual: {
    alignItems: "flex-end",
    backgroundColor: "#0B0B0F",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    height: 150,
    padding: 14,
  },
  gameCell: {
    borderColor: "rgba(255,255,255,0.18)",
    borderWidth: 1,
    width: "14%",
  },
  gameInfo: {
    padding: 15,
  },
  gameGenre: {
    color: "#00FFFF",
    fontFamily: "SpaceMono",
    fontSize: 10,
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },
  intensity: {
    color: "#FFFF00",
    fontFamily: "SpaceMono",
    fontSize: 11,
  },
  cardTitle: {
    color: "#FFFFFF",
    fontFamily: "SpaceMono",
    fontSize: 20,
    lineHeight: 27,
    marginTop: 8,
  },
  geometryText: {
    color: "#FF00FF",
    fontFamily: "SpaceMono",
    fontSize: 11,
    letterSpacing: 1.1,
    marginTop: 12,
    textTransform: "uppercase",
  },
  paletteCard: {
    backgroundColor: "#050505",
    borderColor: "rgba(255,255,255,0.12)",
    borderWidth: 1,
    marginBottom: 14,
    padding: 16,
  },
  paletteCardActive: {
    borderColor: "#FFFF00",
  },
  hexPaletteRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 14,
    marginTop: 18,
    paddingVertical: 6,
  },
  hexSwatch: {
    borderWidth: 1,
    height: 34,
    transform: [{ rotate: "45deg" }],
    width: 34,
  },
  hexSwatchInner: {
    height: 18,
    marginLeft: 7,
    marginTop: 7,
    width: 18,
  },
  paletteMetaRow: {
    borderTopColor: "rgba(255,255,255,0.10)",
    borderTopWidth: 1,
    gap: 6,
    marginTop: 18,
    paddingTop: 12,
  },
  metaText: {
    color: "#A1A1AA",
    fontFamily: "SpaceMono",
    fontSize: 10,
    lineHeight: 16,
    textTransform: "uppercase",
  },
  emptyPanel: {
    alignItems: "center",
    borderColor: "rgba(255,255,255,0.12)",
    borderWidth: 1,
    padding: 24,
  },
  emptyTitle: {
    color: "#FFFFFF",
    fontFamily: "SpaceMono",
    fontSize: 18,
    marginTop: 12,
  },
  saveCard: {
    backgroundColor: "#050505",
    borderColor: "rgba(255,255,255,0.12)",
    borderWidth: 1,
    marginBottom: 12,
    padding: 15,
  },
  signatureBig: {
    color: "#00FFFF",
    fontFamily: "SpaceMono",
    fontSize: 12,
    marginLeft: 10,
  },
  saveFooter: {
    borderTopColor: "rgba(255,255,255,0.10)",
    borderTopWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 14,
    paddingTop: 12,
  },
  tabBar: {
    backgroundColor: "#050505",
    borderTopColor: "rgba(255,255,255,0.14)",
    borderTopWidth: 1,
    flexDirection: "row",
    gap: 8,
    paddingHorizontal: 10,
    paddingTop: 10,
  },
  tabItem: {
    alignItems: "center",
    borderColor: "rgba(255,255,255,0.10)",
    borderWidth: 1,
    flex: 1,
    gap: 3,
    justifyContent: "center",
    minHeight: 54,
  },
  tabItemActive: {
    backgroundColor: "#FFFF00",
    borderColor: "#FFFF00",
  },
  tabText: {
    color: "#A1A1AA",
    fontFamily: "SpaceMono",
    fontSize: 10,
  },
  tabTextActive: {
    color: "#050505",
  },
});
