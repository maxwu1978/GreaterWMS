import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "online.maxsmartwms.app",
  appName: "MaxSmart WMS",
  webDir: "dist",
  server: {
    iosScheme: "capacitor",
  },
  ios: {
    contentInset: "automatic",
  },
};

export default config;
