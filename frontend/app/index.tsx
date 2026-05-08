import { StatusBar } from "expo-status-bar";
import React from "react";
import { ActivityIndicator, Platform, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { WebView } from "react-native-webview";

import { API_BASE } from "../lib/api";

const rendererUrl = `${API_BASE}/tonality-renderer`;

function OriginalStudioFrame() {
  if (Platform.OS === "web") {
    return React.createElement("iframe" as never, {
      src: rendererUrl,
      style: {
        backgroundColor: "#0b0b10",
        border: 0,
        flex: 1,
        height: "100%",
        width: "100%",
      },
      title: "Original Tonality MunkerHex renderer",
    });
  }

  return (
    <WebView
      allowsInlineMediaPlayback
      domStorageEnabled
      javaScriptEnabled
      mixedContentMode="always"
      originWhitelist={["*"]}
      renderLoading={() => (
        <View style={styles.loadingScreen}>
          <ActivityIndicator color="#ffd24a" size="large" />
          <Text style={styles.loadingText}>loading original Tonality renderer…</Text>
        </View>
      )}
      source={{ uri: rendererUrl }}
      startInLoadingState
      style={styles.webview}
      testID="original-tonality-webview"
    />
  );
}

export default function Index() {
  return (
    <SafeAreaView style={styles.safeArea} edges={["top", "left", "right"]}>
      <StatusBar style="light" />
      <OriginalStudioFrame />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    backgroundColor: "#050505",
    flex: 1,
  },
  webview: {
    backgroundColor: "#0b0b10",
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
  controlHeaderText: {
    flex: 1,
    paddingRight: 12,
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
