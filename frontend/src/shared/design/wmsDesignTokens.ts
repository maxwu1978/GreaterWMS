export const wmsDesignTokens = {
  figma: {
    fileKey: "EgmC0PmzGCccExylTDQ3Zb",
    url: "https://www.figma.com/design/EgmC0PmzGCccExylTDQ3Zb",
  },
  color: {
    ink: "#13212c",
    page: "#f2efe8",
    surface: "#ffffff",
    surfaceSoft: "#f7f4ee",
    surfaceWarm: "#fbf8f2",
    mutedText: "#61717d",
    subtleText: "#7f8d98",
    border: "#e3ddd2",
    borderStrong: "#d7d0c4",
    action: "#24507a",
    actionSoft: "#eef3f8",
    success: "#28543b",
    successSoft: "#eef8f0",
    warning: "#91621a",
    warningSoft: "#fff7e8",
    danger: "#9b452a",
    dangerSoft: "#fff1eb",
    accent: "#f7bf45",
  },
  spacing: {
    xs: "4px",
    sm: "8px",
    md: "12px",
    lg: "16px",
    xl: "20px",
    "2xl": "24px",
    "3xl": "32px",
  },
  radius: {
    sm: "8px",
    md: "12px",
    lg: "16px",
    xl: "24px",
    panel: "28px",
    pill: "9999px",
  },
  shadow: {
    card: "0 18px 44px rgba(19, 33, 44, 0.06)",
    raised: "0 24px 60px rgba(19, 33, 44, 0.08)",
    hero: "0 30px 80px rgba(19, 33, 44, 0.16)",
  },
  typography: {
    eyebrow: {
      fontSize: "11px",
      fontWeight: 600,
      letterSpacing: "0.18em",
      textTransform: "uppercase",
    },
    body: {
      fontSize: "14px",
      lineHeight: "22px",
      fontWeight: 400,
    },
    sectionTitle: {
      fontSize: "18px",
      lineHeight: "24px",
      fontWeight: 600,
    },
    pageTitle: {
      fontSize: "30px",
      lineHeight: "36px",
      fontWeight: 600,
    },
  },
} as const;

export type WmsDesignTokens = typeof wmsDesignTokens;
