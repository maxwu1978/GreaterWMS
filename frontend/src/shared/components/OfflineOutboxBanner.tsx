import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, RotateCw, WifiOff } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import {
  getOutboxSummary,
  replayOutbox,
  subscribeOutboxChanges,
  subscribeOutboxSynced,
  type OutboxSummary,
} from "../offline/outbox";
import { useI18n } from "../i18n";

function useOnlineStatus() {
  const [online, setOnline] = useState(() => (typeof navigator === "undefined" ? true : navigator.onLine));

  useEffect(() => {
    const update = () => setOnline(typeof navigator === "undefined" ? true : navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  return online;
}

function useOutboxSummary() {
  const [summary, setSummary] = useState<OutboxSummary>({ pending: 0, synced: 0, failed: 0 });

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      void getOutboxSummary().then((nextSummary) => {
        if (!cancelled) setSummary(nextSummary);
      });
    };
    load();
    const unsubscribe = subscribeOutboxChanges(load);
    const interval = window.setInterval(load, 5000);
    return () => {
      cancelled = true;
      unsubscribe();
      window.clearInterval(interval);
    };
  }, []);

  return summary;
}

export default function OfflineOutboxBanner() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const online = useOnlineStatus();
  const summary = useOutboxSummary();
  const [retrying, setRetrying] = useState(false);
  const actionableCount = summary.pending + summary.failed;

  useEffect(() => {
    return subscribeOutboxSynced(() => {
      void queryClient.invalidateQueries();
    });
  }, [queryClient]);

  if (online && actionableCount === 0) return null;

  const tone = !online
    ? "border-[#e6c06a]/60 bg-[#fff8e8] text-[#7a5300]"
    : summary.failed > 0
      ? "border-[#efb4a8] bg-[#fff1ee] text-[#8f2d19]"
      : "border-[#9ed4b7] bg-[#edf8f1] text-[#1b5f38]";
  const Icon = !online ? WifiOff : summary.failed > 0 ? AlertTriangle : CheckCircle2;
  const title = !online
    ? t("offline.bannerOfflineTitle", "Offline mode")
    : summary.failed > 0
      ? t("offline.bannerFailedTitle", "Offline sync needs attention")
      : t("offline.bannerPendingTitle", "Syncing queued work");
  const body = !online
    ? t("offline.bannerOfflineBody", "{count} actions are queued and will retry when the connection returns.", {
        count: actionableCount,
      })
    : summary.failed > 0
      ? t("offline.bannerFailedBody", "{failed} failed, {pending} pending.", {
          failed: summary.failed,
          pending: summary.pending,
        })
      : t("offline.bannerPendingBody", "{count} queued actions are retrying in the background.", {
          count: summary.pending,
        });

  const handleRetry = async () => {
    setRetrying(true);
    await replayOutbox(true);
    setRetrying(false);
  };

  return (
    <div className={`mb-4 flex flex-col gap-3 rounded-[1rem] border px-4 py-3 shadow-sm sm:flex-row sm:items-center sm:justify-between ${tone}`}>
      <div className="flex min-w-0 items-start gap-3">
        <Icon size={18} className="mt-0.5 shrink-0" />
        <div className="min-w-0">
          <p className="text-sm font-semibold">{title}</p>
          <p className="mt-1 text-sm leading-5">{body}</p>
        </div>
      </div>
      {online && actionableCount > 0 ? (
        <button
          type="button"
          onClick={() => void handleRetry()}
          disabled={retrying}
          className="inline-flex min-h-[40px] shrink-0 items-center justify-center gap-2 rounded-full border border-current/20 bg-white/70 px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] transition hover:bg-white disabled:cursor-wait disabled:opacity-70"
        >
          <RotateCw size={14} className={retrying ? "animate-spin" : ""} />
          {retrying ? t("offline.retrying", "Retrying") : t("offline.retryNow", "Retry now")}
        </button>
      ) : null}
    </div>
  );
}
