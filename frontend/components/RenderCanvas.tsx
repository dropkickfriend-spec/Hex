import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useEffect, useMemo, useRef } from "react";
import { Animated, Easing, Platform, StyleSheet, Text, View } from "react-native";

import type { PalettePreset, RenderConfig, RenderProject } from "../lib/types";

type RenderCanvasProps = {
  url: string;
  palette?: PalettePreset;
  config: RenderConfig;
  latestProject?: RenderProject | null;
  isRendering?: boolean;
};

const DEFAULT_COLORS = ["#00FFFF", "#FF00FF", "#FFFF00", "#050505"];

function normalizeHost(url: string) {
  try {
    const withProtocol = url.match(/^https?:\/\//i) ? url : `https://${url}`;
    return new URL(withProtocol).host.replace("www.", "");
  } catch {
    return "enter-a-site.url";
  }
}

function hashString(value: string) {
  return value.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
}

function WebPreviewBlocks({ host, colors }: { host: string; colors: string[] }) {
  const hash = hashString(host);
  const heroHeight = 72 + (hash % 42);
  const leftWidth = 38 + (hash % 22);

  return (
    <View style={styles.siteBody}>
      <View style={styles.browserTop}>
        <View style={[styles.browserDot, { backgroundColor: colors[1] || "#FF00FF" }]} />
        <View style={[styles.browserDot, { backgroundColor: colors[2] || "#FFFF00" }]} />
        <View style={[styles.browserDot, { backgroundColor: colors[0] || "#00FFFF" }]} />
        <Text style={styles.browserUrl} numberOfLines={1}>{host}</Text>
      </View>

      <View style={[styles.heroBlock, { height: heroHeight, borderColor: colors[0] }]}>
        <View style={[styles.heroOrb, { backgroundColor: colors[2] || "#FFFF00" }]} />
        <View style={styles.heroTextStack}>
          <View style={[styles.heroLine, { width: "74%", backgroundColor: colors[0] }]} />
          <View style={[styles.heroLine, { width: "48%", backgroundColor: colors[1] }]} />
          <View style={[styles.heroLine, { width: "62%", backgroundColor: colors[2] }]} />
        </View>
      </View>

      <View style={styles.contentGrid}>
        <View style={[styles.contentColumn, { width: `${leftWidth}%` }]}>
          {[0, 1, 2].map((item) => (
            <View key={`left-${item}`} style={[styles.contentBar, { backgroundColor: colors[item % colors.length] }]} />
          ))}
        </View>
        <View style={styles.cardCluster}>
          {[0, 1, 2, 3].map((item) => (
            <View
              key={`card-${item}`}
              style={[
                styles.miniCard,
                { borderColor: colors[(item + 1) % colors.length], opacity: 0.75 + item * 0.05 },
              ]}
            />
          ))}
        </View>
      </View>
    </View>
  );
}

function HexOverlay({ colors }: { colors: string[] }) {
  const cells = useMemo(() => Array.from({ length: 36 }, (_, index) => index), []);

  return (
    <View style={styles.hexLayer}>
      {cells.map((cell) => {
        const row = Math.floor(cell / 6);
        const col = cell % 6;
        const offset = row % 2 ? 18 : 0;
        return (
          <View
            key={`hex-${cell}`}
            style={[
              styles.hexCell,
              {
                left: col * 54 + offset - 20,
                top: row * 34 - 10,
                borderColor: colors[cell % colors.length],
              },
            ]}
          >
            <View style={[styles.hexFace, { backgroundColor: colors[(cell + 1) % colors.length] }]} />
          </View>
        );
      })}
    </View>
  );
}

function StripeOverlay({ config, colors }: { config: RenderConfig; colors: string[] }) {
  const phase = useRef(new Animated.Value(0)).current;
  const lineCount = Math.max(14, config.density * 2);
  const opacity = config.opacity / 100;
  const translate = phase.interpolate({ inputRange: [0, 1], outputRange: [0, config.density * 2] });

  useEffect(() => {
    phase.setValue(0);
    const animation = Animated.loop(
      Animated.timing(phase, {
        toValue: 1,
        duration: config.animation_speed * 1000,
        easing: Easing.linear,
        useNativeDriver: Platform.OS !== "web",
      }),
    );
    animation.start();
    return () => animation.stop();
  }, [config.animation_speed, phase]);

  const renderLines = (prefix: string, vertical = false, diagonal = false) => (
    <Animated.View
      style={[
        styles.stripeLayer,
        {
          opacity,
          transform: [
            { translateX: vertical || diagonal ? translate : 0 },
            { translateY: vertical ? 0 : translate },
            { rotate: diagonal ? "-24deg" : "0deg" },
          ],
        },
      ]}
    >
      {Array.from({ length: lineCount }, (_, index) => (
        <View
          key={`${prefix}-${index}`}
          style={[
            vertical ? styles.verticalStripe : styles.horizontalStripe,
            {
              [vertical ? "left" : "top"]: index * config.density - config.density,
              [vertical ? "width" : "height"]: config.thickness,
              backgroundColor: index % 2 ? colors[0] : colors[1] || "#FFFFFF",
            },
          ]}
        />
      ))}
    </Animated.View>
  );

  if (config.stripe_mode === "grid") {
    return (
      <View style={StyleSheet.absoluteFill}>
        {renderLines("horizontal")}
        {renderLines("vertical", true)}
      </View>
    );
  }

  return renderLines(config.stripe_mode, config.stripe_mode === "vertical", config.stripe_mode === "diagonal");
}

export function RenderCanvas({ url, palette, config, latestProject, isRendering }: RenderCanvasProps) {
  const colors = palette?.colors?.length ? palette.colors : DEFAULT_COLORS;
  const host = normalizeHost(url);

  return (
    <View style={styles.canvasShell} testID="munker-render-canvas">
      <View style={styles.canvasHeader}>
        <View>
          <Text style={styles.canvasKicker}>LIVE LOCAL STYLE RENDER</Text>
          <Text style={styles.canvasTitle} numberOfLines={1}>{host}</Text>
        </View>
        <View style={styles.signatureBadge}>
          <MaterialCommunityIcons name="hexagon-multiple-outline" size={18} color="#00FFFF" />
          <Text style={styles.signatureText}>{latestProject?.signature || "UNSAVED"}</Text>
        </View>
      </View>

      <View style={styles.canvasStage}>
        <WebPreviewBlocks host={host} colors={colors} />
        {config.hex_enabled ? <HexOverlay colors={colors} /> : null}
        <StripeOverlay config={config} colors={colors} />
        <View style={styles.vignette} />
        {isRendering ? (
          <View style={styles.renderingPlate}>
            <MaterialCommunityIcons name="auto-fix" size={22} color="#FFFF00" />
            <Text style={styles.renderingText}>calibrating Munker field…</Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  canvasShell: {
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.14)",
    backgroundColor: "#050505",
    overflow: "hidden",
  },
  canvasHeader: {
    alignItems: "center",
    borderBottomColor: "rgba(255,255,255,0.12)",
    borderBottomWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  canvasKicker: {
    color: "#A1A1AA",
    fontFamily: "SpaceMono",
    fontSize: 9,
    letterSpacing: 1.4,
  },
  canvasTitle: {
    color: "#FFFFFF",
    fontFamily: "SpaceMono",
    fontSize: 17,
    marginTop: 4,
    maxWidth: 180,
  },
  signatureBadge: {
    alignItems: "center",
    borderColor: "#00FFFF",
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: "row",
    gap: 6,
    minHeight: 38,
    paddingHorizontal: 10,
  },
  signatureText: {
    color: "#00FFFF",
    fontFamily: "SpaceMono",
    fontSize: 10,
  },
  canvasStage: {
    height: 300,
    overflow: "hidden",
  },
  siteBody: {
    backgroundColor: "#0B0B0F",
    flex: 1,
    padding: 14,
  },
  browserTop: {
    alignItems: "center",
    borderColor: "rgba(255,255,255,0.18)",
    borderWidth: 1,
    flexDirection: "row",
    gap: 7,
    height: 34,
    paddingHorizontal: 10,
  },
  browserDot: {
    borderRadius: 999,
    height: 8,
    width: 8,
  },
  browserUrl: {
    color: "#A1A1AA",
    flex: 1,
    fontFamily: "SpaceMono",
    fontSize: 10,
    marginLeft: 4,
  },
  heroBlock: {
    borderWidth: 1,
    flexDirection: "row",
    marginTop: 12,
    overflow: "hidden",
    padding: 14,
  },
  heroOrb: {
    borderRadius: 999,
    height: 58,
    opacity: 0.9,
    width: 58,
  },
  heroTextStack: {
    flex: 1,
    gap: 10,
    justifyContent: "center",
    marginLeft: 14,
  },
  heroLine: {
    height: 8,
  },
  contentGrid: {
    flex: 1,
    flexDirection: "row",
    gap: 12,
    marginTop: 12,
  },
  contentColumn: {
    borderColor: "rgba(255,255,255,0.14)",
    borderWidth: 1,
    gap: 9,
    padding: 12,
  },
  contentBar: {
    height: 12,
    opacity: 0.85,
  },
  cardCluster: {
    flex: 1,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  miniCard: {
    borderWidth: 1,
    height: "45%",
    width: "46%",
  },
  hexLayer: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0.34,
  },
  hexCell: {
    borderWidth: 1,
    height: 30,
    position: "absolute",
    transform: [{ rotate: "45deg" }, { skewX: "-12deg" }],
    width: 30,
  },
  hexFace: {
    bottom: 7,
    height: 8,
    opacity: 0.42,
    position: "absolute",
    right: 7,
    width: 8,
  },
  stripeLayer: {
    ...StyleSheet.absoluteFillObject,
    height: 460,
    left: -70,
    top: -70,
    width: 520,
  },
  horizontalStripe: {
    left: 0,
    position: "absolute",
    width: 520,
  },
  verticalStripe: {
    height: 460,
    position: "absolute",
    top: 0,
  },
  vignette: {
    ...StyleSheet.absoluteFillObject,
    borderColor: "rgba(255,255,255,0.08)",
    borderWidth: 1,
  },
  renderingPlate: {
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: "rgba(5,5,5,0.86)",
    borderColor: "#FFFF00",
    borderWidth: 1,
    flexDirection: "row",
    gap: 8,
    minHeight: 46,
    paddingHorizontal: 14,
    position: "absolute",
    top: 126,
  },
  renderingText: {
    color: "#FFFF00",
    fontFamily: "SpaceMono",
    fontSize: 12,
  },
});