/**
 * PWA Barcode Scanner — uses Web Camera API for barcode scanning.
 *
 * Works on any modern phone browser without app installation.
 * Uses the BarcodeDetector API when available, with ZXing as a browser fallback.
 *
 * Usage:
 *   <BarcodeScanner onScan={(barcode) => handleScan(barcode)} context="receiving" />
 */

import { BrowserMultiFormatReader, type IScannerControls } from "@zxing/browser";
import { useEffect, useRef, useState, useCallback, useId, type ChangeEvent } from "react";
import { useI18n } from "../shared/i18n";

type ScanSource = "scan" | "photo" | "manual";

type PendingDetectedCode = {
  code: string;
  source: Exclude<ScanSource, "manual">;
};

interface BarcodeScannerProps {
  onScan: (barcode: string, source?: ScanSource) => void;
  context?: string;
  placeholder?: string;
  suggestedCodes?: Array<{ label: string; value: string }>;
  manualHintTitle?: string;
  manualHintBody?: string;
  deviceHint?: string;
}

export default function BarcodeScanner({
  onScan,
  context = "scan",
  placeholder = "Scan barcode or type manually...",
  suggestedCodes = [],
  manualHintTitle,
  manualHintBody,
  deviceHint,
}: BarcodeScannerProps) {
  const { t } = useI18n();
  const videoRef = useRef<HTMLVideoElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);
  const suggestedCodesListId = useId();
  const audioContextRef = useRef<AudioContext | null>(null);
  const lastDetectedRef = useRef<string>("");
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const fallbackScannerRef = useRef<IScannerControls | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [lastScan, setLastScan] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [hasBarcodeDetector, setHasBarcodeDetector] = useState(false);
  const [supportedFormats, setSupportedFormats] = useState<string[]>([]);
  const [photoPending, setPhotoPending] = useState(false);
  const [photoName, setPhotoName] = useState("");
  const [manualValue, setManualValue] = useState("");
  const [pendingDetectedCode, setPendingDetectedCode] = useState<PendingDetectedCode | null>(null);
  const [copiedSuggestedCode, setCopiedSuggestedCode] = useState("");

  const normalizeManualCode = useCallback((value: string) => {
    const trimmed = value.trim();
    const prefixed = trimmed.match(
      /^(tracking|carton|customer|internal|label|barcode|code|track|ref|reference|\u8ffd\u8e2a|\u8ddf\u8e2a|\u7bb1\u53f7|\u7bb1\u551b|\u5ba2\u6237|\u5185\u90e8|\u6761\u7801|\u4ee3\u7801)\s*[:：]\s*(.+)$/i,
    );
    return (prefixed?.[2] || trimmed).trim();
  }, []);

  useEffect(() => {
    const loadBarcodeSupport = async () => {
      if (!("BarcodeDetector" in window)) return;
      setHasBarcodeDetector(true);

      try {
        const BarcodeDetectorCtor = window.BarcodeDetector as {
          getSupportedFormats?: () => Promise<string[]>;
        };
        if (typeof BarcodeDetectorCtor.getSupportedFormats === "function") {
          const formats = await BarcodeDetectorCtor.getSupportedFormats();
          setSupportedFormats(formats);
        }
      } catch {
        // Some browsers expose BarcodeDetector but not supported format introspection.
      }
    };

    void loadBarcodeSupport();
  }, []);

  const focusInput = useCallback(() => {
    requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select?.();
    });
  }, []);

  const playTone = useCallback((tone: "success" | "error") => {
    if (typeof window === "undefined") return;

    try {
      const AudioCtx = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioCtx) return;
      const context = audioContextRef.current || new AudioCtx();
      audioContextRef.current = context;

      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = "sine";
      oscillator.frequency.value = tone === "success" ? 880 : 320;
      gain.gain.value = tone === "success" ? 0.04 : 0.05;
      oscillator.connect(gain);
      gain.connect(context.destination);
      const now = context.currentTime;
      gain.gain.setValueAtTime(gain.gain.value, now);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + (tone === "success" ? 0.12 : 0.18));
      oscillator.start(now);
      oscillator.stop(now + (tone === "success" ? 0.12 : 0.18));
    } catch {
      // Sound is optional; ignore if browser blocks audio.
    }
  }, []);

  const getDetectionFormats = useCallback(() => {
    const desiredFormats = [
      "code_128",
      "code_39",
      "code_93",
      "codabar",
      "ean_13",
      "ean_8",
      "upc_a",
      "upc_e",
      "itf",
      "qr_code",
      "data_matrix",
      "aztec",
      "pdf417",
    ];

    if (!supportedFormats.length) {
      return desiredFormats;
    }

    const available = desiredFormats.filter((format) => supportedFormats.includes(format));
    return available.length ? available : supportedFormats;
  }, [supportedFormats]);

  const closeCameraPreview = useCallback(() => {
    fallbackScannerRef.current?.stop();
    fallbackScannerRef.current = null;
    const stream = (videoRef.current?.srcObject as MediaStream | null) || cameraStreamRef.current;
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
    }
    if (videoRef.current?.srcObject) {
      videoRef.current.srcObject = null;
    }
    cameraStreamRef.current = null;
    setCameraActive(false);
  }, []);

  const submitScan = useCallback(
    (barcode: string, source: ScanSource = "scan") => {
      const normalized = normalizeManualCode(barcode);
      if (!normalized) return;
      lastDetectedRef.current = normalized;
      setLastScan(normalized);
      setPendingDetectedCode(null);
      setError("");
      playTone("success");
      onScan(normalized, source);
      focusInput();
    },
    [focusInput, normalizeManualCode, onScan, playTone],
  );

  const copySuggestedCode = useCallback(
    async (barcode: string) => {
      const normalized = normalizeManualCode(barcode);
      if (!normalized) return;

      try {
        if (!navigator.clipboard?.writeText) {
          throw new Error("Clipboard API unavailable");
        }
        await navigator.clipboard.writeText(normalized);
        setCopiedSuggestedCode(normalized);
      } catch {
        setManualValue(normalized);
        focusInput();
      }
    },
    [focusInput, normalizeManualCode],
  );

  const holdDetectedCode = useCallback(
    (barcode: string, source: Exclude<ScanSource, "manual">) => {
      const normalized = normalizeManualCode(barcode);
      if (!normalized) return;
      lastDetectedRef.current = normalized;
      setPendingDetectedCode({ code: normalized, source });
      setLastScan("");
      setError("");
      playTone("success");
      if (source === "scan") {
        closeCameraPreview();
      }
    },
    [closeCameraPreview, normalizeManualCode, playTone],
  );

  const detectBarcode = useCallback(
    async (stream: MediaStream) => {
      // @ts-ignore — BarcodeDetector is not in all TS libs yet
      const detector = new BarcodeDetector({
        formats: getDetectionFormats(),
      });

      const detect = async () => {
        if (!videoRef.current || !stream.active) return;

        try {
          const barcodes = await detector.detect(videoRef.current);
          if (barcodes.length > 0) {
            const barcode = barcodes[0].rawValue;
            if (barcode !== lastDetectedRef.current) {
              holdDetectedCode(barcode, "scan");
              // Brief pause to avoid duplicate scans
              await new Promise((r) => setTimeout(r, 1500));
            }
          }
        } catch {
          // Detection frame failed, continue
        }

        if (stream.active) {
          requestAnimationFrame(detect);
        }
      };

      detect();
    },
    [getDetectionFormats, holdDetectedCode],
  );

  const startFallbackDetection = useCallback(
    async (stream: MediaStream) => {
      if (!videoRef.current || !stream.active) return;

      try {
        fallbackScannerRef.current?.stop();
        const reader = new BrowserMultiFormatReader(undefined, {
          delayBetweenScanAttempts: 250,
          delayBetweenScanSuccess: 1500,
          tryPlayVideoTimeout: 5000,
        });
        fallbackScannerRef.current = await reader.decodeFromStream(
          stream,
          videoRef.current,
          (result) => {
            const barcode = result?.getText();
            if (!barcode || barcode === lastDetectedRef.current) return;
            holdDetectedCode(barcode, "scan");
          },
        );
      } catch {
        setError(
          t(
            "scanner.fallbackFailed",
            "Camera opened, but barcode recognition could not start. Use manual input or Read photo instead.",
          ),
        );
        playTone("error");
        focusInput();
      }
    },
    [focusInput, holdDetectedCode, playTone, t],
  );

  const attachCameraStream = useCallback(
    (stream: MediaStream) => {
      const attach = () => {
        if (cameraStreamRef.current !== stream) return;
        if (!videoRef.current) {
          requestAnimationFrame(attach);
          return;
        }
        videoRef.current.srcObject = stream;
        if (hasBarcodeDetector) {
          void detectBarcode(stream);
        } else {
          void startFallbackDetection(stream);
        }
      };
      requestAnimationFrame(attach);
    },
    [detectBarcode, hasBarcodeDetector, startFallbackDetection],
  );

  const startCamera = useCallback(async () => {
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError(t("scanner.cameraUnavailable", "Camera scanning is not available in this browser. Use manual input instead."));
        playTone("error");
        focusInput();
        return;
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" }, // Rear camera
      });
      cameraStreamRef.current = stream;
      setPendingDetectedCode(null);
      setCameraActive(true);
      setError("");
      attachCameraStream(stream);
    } catch {
      setError(t("scanner.cameraDenied", "Camera access denied. Use manual input instead."));
      playTone("error");
      focusInput();
    }
  }, [attachCameraStream, focusInput, playTone, t]);

  const detectFromPhoto = useCallback(
    async (file: File) => {
      setPhotoPending(true);
      setPhotoName(file.name);

      try {
        if (hasBarcodeDetector && "createImageBitmap" in window) {
          // @ts-ignore — BarcodeDetector is not in all TS libs yet
          const detector = new BarcodeDetector({
            formats: getDetectionFormats(),
          });
          const bitmap = await createImageBitmap(file);
          const barcodes = await detector.detect(bitmap);
          bitmap.close?.();

          if (barcodes.length && barcodes[0]?.rawValue) {
            holdDetectedCode(barcodes[0].rawValue, "photo");
            return;
          }
        }

        const reader = new BrowserMultiFormatReader(undefined, {
          delayBetweenScanAttempts: 250,
          tryPlayVideoTimeout: 5000,
        });
        const imageUrl = URL.createObjectURL(file);
        try {
          const result = await reader.decodeFromImageUrl(imageUrl);
          const barcode = result.getText();
          if (!barcode) throw new Error("No barcode text");
          holdDetectedCode(barcode, "photo");
        } finally {
          URL.revokeObjectURL(imageUrl);
        }
      } catch {
        setError(
          t(
            "scanner.photoReadFailed",
            "The system could not read a barcode from this photo. Try again with a sharper image.",
          ),
        );
        playTone("error");
        focusInput();
      } finally {
        setPhotoPending(false);
      }
    },
    [focusInput, getDetectionFormats, hasBarcodeDetector, holdDetectedCode, playTone, t],
  );

  const stopCamera = useCallback(() => {
    closeCameraPreview();
    focusInput();
  }, [closeCameraPreview, focusInput]);

  // Manual input handler
  const submitManualInput = useCallback(() => {
    const value = manualValue.trim() || inputRef.current?.value.trim();
    if (!value) return;
    submitScan(value, "manual");
    setManualValue("");
  }, [manualValue, submitScan]);

  const handleManualInput = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submitManualInput();
    }
  };

  const handlePhotoSelection = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await detectFromPhoto(file);
    e.target.value = "";
  };

  const confirmDetectedCode = useCallback(() => {
    if (!pendingDetectedCode) return;
    submitScan(pendingDetectedCode.code, pendingDetectedCode.source);
  }, [pendingDetectedCode, submitScan]);

  const scanAgain = useCallback(() => {
    const shouldRestartCamera = pendingDetectedCode?.source === "scan";
    lastDetectedRef.current = "";
    setPendingDetectedCode(null);
    setError("");
    if (shouldRestartCamera) {
      void startCamera();
    } else {
      focusInput();
    }
  }, [focusInput, pendingDetectedCode, startCamera]);

  const resolvedManualHintTitle =
    manualHintTitle || t("scanner.manualInputHintTitle", "Manual input hint");
  const resolvedManualHintBody =
    manualHintBody ||
    (context === "picking"
      ? t(
          "scanner.pickingManualInputHintBody",
          "Use the expected location or SKU code shown in this pick task. Scanner guns can type directly into this field.",
        )
      : t(
          "scanner.manualInputHintBody",
          "No saved tracking, carton, or customer barcode is available for this inbound yet. Add a package code first, or scan the printed internal receiving label.",
        ));
  const resolvedDeviceHint =
    deviceHint ||
    t(
      "scanner.deviceHint",
      "Type or scan a code into the field, then press Enter or Use code. Use Scan to open the phone camera for live scanning, or Read photo to decode a label image when the browser supports it.",
    );

  // Cleanup camera on unmount
  useEffect(() => {
    return () => stopCamera();
  }, [stopCamera]);

  useEffect(() => {
    if (!cameraActive && !photoPending && !pendingDetectedCode) {
      focusInput();
    }
  }, [cameraActive, focusInput, pendingDetectedCode, photoPending]);

  const primarySuggestedCode = suggestedCodes[0] || null;
  const additionalSuggestedCodes = suggestedCodes.slice(1);

  return (
    <div className="space-y-3">
      {/* Manual input — always available, works with RF guns and keyboard */}
      <div className="space-y-2">
        <input
          ref={inputRef}
          type="text"
          value={manualValue}
          onChange={(event) => setManualValue(event.target.value)}
          placeholder={placeholder}
          list={suggestedCodes.length ? suggestedCodesListId : undefined}
          onKeyDown={handleManualInput}
          autoFocus
          className="flex-1 min-h-[52px] w-full px-4 py-3 border border-gray-300 rounded-xl text-lg
                     focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        {suggestedCodes.length ? (
          <datalist id={suggestedCodesListId}>
            {suggestedCodes.map((code) => (
              <option key={`${code.label}-${code.value}`} value={code.value}>
                {code.label}
              </option>
            ))}
          </datalist>
        ) : null}

        {/* Camera view */}
        {cameraActive && (
          <div className="relative overflow-hidden rounded-xl bg-black shadow-inner ring-1 ring-[#d8e3ef]">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              className="min-h-[220px] w-full max-h-[320px] object-cover md:max-h-64"
            />
            {!hasBarcodeDetector && (
              <div className="absolute bottom-0 left-0 right-0 bg-[#f4c74a] text-[#13212c] text-xs p-2 text-center">
                {t(
                  "scanner.backupScanner",
                  "Backup scanner active. Hold the barcode steady inside the camera view."
                )}
              </div>
            )}
          </div>
        )}

        {pendingDetectedCode ? (
          <div className="rounded-xl border border-[#b7d2ff] bg-[#f3f8ff] p-3">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#51606b]">
              {t("scanner.detectedCode", "Detected code")}
            </p>
            <code className="mt-2 block break-all rounded-lg bg-white px-3 py-2 text-sm font-semibold text-[#13212c] ring-1 ring-[#d8e3ef]">
              {pendingDetectedCode.code}
            </code>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={confirmDetectedCode}
                className="min-h-[48px] rounded-xl bg-[#13212c] px-3 py-2 text-sm font-semibold text-white"
              >
                {t("scanner.confirmDetectedCode", "Use this code")}
              </button>
              <button
                type="button"
                onClick={scanAgain}
                className="min-h-[48px] rounded-xl border border-[#d5dde5] bg-white px-3 py-2 text-sm font-semibold text-[#13212c]"
              >
                {pendingDetectedCode.source === "scan"
                  ? t("scanner.scanAgain", "Scan again")
                  : t("scanner.chooseAnotherPhoto", "Choose another")}
              </button>
            </div>
          </div>
        ) : null}

        <div className="grid grid-cols-2 gap-2 md:flex">
          <button
            onClick={
              manualValue.trim()
                ? submitManualInput
                : cameraActive
                  ? stopCamera
                  : startCamera
            }
            className={`min-h-[52px] rounded-xl px-4 py-3 font-medium ${
              cameraActive
                ? "bg-red-500 text-white"
                : "bg-blue-500 text-white"
            }`}
          >
            {manualValue.trim()
              ? t("scanner.useCode", "Use code")
              : cameraActive
                ? t("scanner.stopScan", "Stop scan")
                : t("scanner.scan", "Scan")}
          </button>
          <button
            type="button"
            onClick={() => photoInputRef.current?.click()}
            disabled={photoPending}
            className="min-h-[52px] rounded-xl border border-gray-300 bg-white px-4 py-3 font-medium text-[#13212c] disabled:opacity-60"
          >
            {photoPending ? t("scanner.readingPhoto", "Reading photo...") : t("scanner.photo", "Read photo")}
          </button>
        </div>
        <input
          ref={photoInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          onChange={handlePhotoSelection}
          className="hidden"
        />
      </div>
      {manualValue.trim() ? (
        <p className="text-xs text-[#51606b]">
          {t("scanner.manualReady", "Ready to use: {code}", { code: normalizeManualCode(manualValue) })}
        </p>
      ) : null}

      <div className="rounded-xl border border-[#d8e3ef] bg-[#f7fbff] px-3 py-2">
        {primarySuggestedCode ? (
          <>
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#51606b]">
                {t("scanner.suggestedCode", "Suggested code")}
              </p>
              {additionalSuggestedCodes.length ? (
                <span className="hidden rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-[#6b7a88] md:inline-flex">
                  {t("scanner.moreSuggestedCodes", "{count} more", {
                    count: String(additionalSuggestedCodes.length),
                  })}
                </span>
              ) : null}
            </div>

            <div className="mt-2 rounded-xl border border-[#cbd8e5] bg-white p-3 md:hidden">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-[#4977c8]">{primarySuggestedCode.label}</span>
                <button
                  type="button"
                  onClick={() => copySuggestedCode(primarySuggestedCode.value)}
                  className="min-h-[36px] rounded-full border border-[#d8e3ef] bg-white px-3 text-xs font-semibold text-[#13212c]"
                >
                  {copiedSuggestedCode === normalizeManualCode(primarySuggestedCode.value)
                    ? t("scanner.copiedCode", "Copied")
                    : t("scanner.copyCode", "Copy code")}
                </button>
              </div>
              <code className="mt-2 block select-all break-all rounded-lg bg-[#f7fbff] px-3 py-2 font-mono text-sm leading-5 text-[#13212c]">
                {primarySuggestedCode.value}
              </code>
              <button
                type="button"
                onClick={() => submitScan(primarySuggestedCode.value, "manual")}
                className="mt-2 min-h-[44px] w-full rounded-xl bg-[#13212c] px-3 py-2 text-sm font-semibold text-white"
              >
                {t("scanner.useSuggestedCode", "Use this code")}
              </button>
            </div>

            {additionalSuggestedCodes.length ? (
              <details className="mt-2 md:hidden">
                <summary className="cursor-pointer list-none rounded-xl border border-[#d8e3ef] bg-white px-3 py-2 text-xs font-semibold text-[#51606b]">
                  {t("scanner.showOtherSuggestedCodes", "Show other codes ({count})", {
                    count: String(additionalSuggestedCodes.length),
                  })}
                </summary>
                <div className="mt-2 flex flex-col gap-2">
                  {additionalSuggestedCodes.map((code) => (
                    <div
                      key={`${code.label}-${code.value}`}
                      className="rounded-xl border border-[#cbd8e5] bg-white p-3 text-[#13212c]"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-[#4977c8]">{code.label}</span>
                        <button
                          type="button"
                          onClick={() => copySuggestedCode(code.value)}
                          className="min-h-[34px] rounded-full border border-[#d8e3ef] bg-white px-3 text-[11px] font-semibold text-[#13212c]"
                        >
                          {copiedSuggestedCode === normalizeManualCode(code.value)
                            ? t("scanner.copiedCode", "Copied")
                            : t("scanner.copyCode", "Copy code")}
                        </button>
                      </div>
                      <code className="mt-2 block select-all break-all rounded-lg bg-[#f7fbff] px-3 py-2 font-mono text-xs leading-5">
                        {code.value}
                      </code>
                      <button
                        type="button"
                        onClick={() => submitScan(code.value, "manual")}
                        className="mt-2 min-h-[40px] w-full rounded-xl border border-[#d8e3ef] bg-white px-3 py-2 text-xs font-semibold text-[#13212c]"
                      >
                        {t("scanner.useSuggestedCode", "Use this code")}
                      </button>
                    </div>
                  ))}
                </div>
              </details>
            ) : null}

            <div className="mt-2 hidden flex-wrap gap-2 md:flex">
              {suggestedCodes.map((code) => (
                <button
                  key={`${code.label}-${code.value}`}
                  type="button"
                  onClick={() => submitScan(code.value, "manual")}
                  className="inline-flex items-center gap-2 rounded-full border border-[#cbd8e5] bg-white px-3 py-1 text-left text-xs text-[#13212c] transition hover:border-[#7da9ff] hover:bg-[#eef5ff]"
                >
                  <span className="font-semibold text-[#4977c8]">{code.label}</span>
                  <span className="font-mono">{code.value}</span>
                </button>
              ))}
            </div>
          </>
        ) : (
          <>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#51606b]">
              {resolvedManualHintTitle}
            </p>
            <p className="mt-1 text-xs leading-5 text-[#5c6b76]">
              {resolvedManualHintBody}
            </p>
          </>
        )}
      </div>

      {/* Status */}
      {error && <p className="text-red-500 text-sm">{error}</p>}
      {lastScan && (
        <div className="flex flex-col gap-1 text-sm sm:flex-row sm:items-start sm:gap-2">
          <span className="shrink-0 font-medium text-green-600">{t("scanner.lastScan", "Last scan:")}</span>
          <code className="block max-w-full select-all break-all rounded bg-gray-100 px-2 py-1 font-mono leading-5 text-[#13212c]">
            {lastScan}
          </code>
        </div>
      )}
      {photoName ? (
        <p className="text-xs text-gray-500">
          {t("scanner.lastPhoto", "Last photo:")} {photoName}
        </p>
      ) : null}
      <p className="text-xs text-[#6b7280] md:hidden">
        {t("scanner.mobileDeviceHint", "Type a code, press Enter, or use Scan.")}
      </p>
      <p className="hidden text-xs text-[#6b7280] md:block">
        {resolvedDeviceHint}
      </p>
      {hasBarcodeDetector && supportedFormats.length > 0 ? (
        <p className="hidden text-[11px] text-[#94a3b8] md:block">
          {t("scanner.supportedFormats", "Supported scan formats")}: {supportedFormats.join(", ")}
        </p>
      ) : null}
    </div>
  );
}
