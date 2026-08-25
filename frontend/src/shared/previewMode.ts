export function isGreaterWmsPreviewMode(): boolean {
  if (typeof window === "undefined") return false;
  return import.meta.env.VITE_PREVIEW_MODE === "1" || new URLSearchParams(window.location.search).get("greaterwms_preview") === "1";
}
