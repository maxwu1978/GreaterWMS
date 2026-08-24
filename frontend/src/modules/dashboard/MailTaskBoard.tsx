import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, RefreshCw } from "lucide-react";
import { useAuthStore } from "../../shared/hooks/useAuth";
import {
  decideOutboundApproval,
  fetchMailTasks,
  type MailTaskStatus,
  type MailTaskSummary,
  updateMailTaskStatus,
} from "../../shared/api/mailtasks";
import { queryKeys } from "../../shared/api/queryKeys";

const statusClass: Record<string, string> = {
  "Needs Maggie Processing": "border-[#c8d3e4] bg-[#eef4fc] text-[#345d8e]",
  "Needs Sunny Review": "border-[#e3bd73] bg-[#fff8e8] text-[#99651d]",
  "Awaiting Sunny Approval": "border-[#d69a93] bg-[#fff1ef] text-[#9a3f38]",
  "Ready for WMS": "border-[#9ccfb0] bg-[#edf9f1] text-[#2d7047]",
  "Needs Review": "border-[#d69a93] bg-[#fff1ef] text-[#9a3f38]",
  Blocked: "border-[#d69a93] bg-[#fff1ef] text-[#9a3f38]",
};

function canAdvance(task: MailTaskSummary): MailTaskStatus | null {
  if (task.task_status === "Needs Maggie Processing") return "Needs Sunny Review";
  if (task.task_status === "Needs Sunny Review") return "Awaiting Sunny Approval";
  if (task.task_status === "Ready for WMS") return "WMS In Progress";
  return null;
}

function MailTaskRow({ task, canApprove }: { task: MailTaskSummary; canApprove: boolean }) {
  const queryClient = useQueryClient();
  const statusMutation = useMutation({
    mutationFn: (nextStatus: MailTaskStatus) => updateMailTaskStatus(task.task_key, nextStatus),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.mailTasks.list() }),
  });
  const approvalMutation = useMutation({
    mutationFn: () => decideOutboundApproval(task.task_key, "approve", "Approved in GreaterWMS Dashboard"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.mailTasks.list() }),
  });
  const nextStatus = canAdvance(task);
  const isBusy = statusMutation.isPending || approvalMutation.isPending;

  return (
    <div className="grid gap-3 border-t border-[#e1e4e8] px-4 py-4 sm:grid-cols-[minmax(0,1.4fr)_140px_150px_120px_auto] sm:items-center">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className={`inline-flex border px-2 py-1 text-[10px] font-bold tracking-[0.1em] ${statusClass[task.task_status] || "border-[#d0d0d0] bg-[#f7f7f7] text-[#555]"}`}>
            {task.task_status}
          </span>
          {task.exception_flag && <AlertTriangle size={14} className="text-[#c9574f]" aria-label="Task exception" />}
        </div>
        <p className="mt-2 truncate font-semibold text-[#202020]">{task.subject || task.task_key}</p>
        <p className="truncate font-mono text-[11px] text-[#7b8490]">{task.task_key}</p>
      </div>
      <div className="text-xs text-[#4d5662]">
        <p className="font-semibold">{task.record_type} · {task.direction}</p>
        <p className="mt-1">Owner: {task.task_owner || "Unassigned"}</p>
      </div>
      <div className="text-xs text-[#4d5662]">
        <p>Physical: {task.physical_execution_owner || "Unassigned"}</p>
        <p className="mt-1">Approval: {task.approval_status}</p>
      </div>
      <div className="text-xs text-[#4d5662]">
        {task.wms_doc_no ? `${task.wms_system || "WMS"}: ${task.wms_doc_no}` : "WMS reference pending"}
      </div>
      <div className="flex flex-wrap gap-2 sm:justify-end">
        {task.task_status === "Awaiting Sunny Approval" && canApprove && (
          <button
            type="button"
            disabled={isBusy}
            onClick={() => approvalMutation.mutate()}
            className="inline-flex items-center gap-1 border border-[#5d936d] bg-[#edf9f1] px-3 py-2 text-xs font-semibold text-[#2d7047] hover:bg-[#dff2e5] disabled:opacity-50"
          >
            <Check size={13} /> Approve OB
          </button>
        )}
        {nextStatus && (
          <button
            type="button"
            disabled={isBusy}
            onClick={() => statusMutation.mutate(nextStatus)}
            className="border border-[#9aa4bb] bg-white px-3 py-2 text-xs font-semibold text-[#4c5d82] hover:border-[#5d6b8b] hover:bg-[#5d6b8b] hover:text-white disabled:opacity-50"
          >
            {nextStatus === "WMS In Progress" ? "Start WMS" : nextStatus}
          </button>
        )}
      </div>
    </div>
  );
}

export default function MailTaskBoard() {
  const permissions = useAuthStore((state) => state.permissions);
  const canView = permissions.includes("*") || permissions.includes("mailtask.execute") || permissions.includes("mailtask.manage");
  const canApprove = permissions.includes("*") || permissions.includes("mailtask.approve_outbound");
  const { data = [], isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: queryKeys.mailTasks.list(),
    queryFn: () => fetchMailTasks({ limit: 100 }),
    enabled: canView,
    refetchInterval: canView ? 30_000 : false,
  });

  if (!canView) return null;

  return (
    <section className="mt-6 border border-[#cfcfcf] bg-white shadow-[0_4px_14px_rgba(0,0,0,0.08)]" data-testid="mailtask-board" aria-label="MailTask work queue">
      <div className="flex flex-wrap items-end justify-between gap-4 bg-[#39415f] px-5 py-5 text-white sm:px-6">
        <div>
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-[#c9d1e0]">Mail to task</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">Inbound information queue</h2>
          <p className="mt-1 text-xs text-[#d7deea]">Agent email intake · Maggie processing · Sunny outbound approval · Mark physical execution</p>
        </div>
        <button
          type="button"
          onClick={() => void refetch()}
          className="inline-flex items-center gap-2 border border-white/30 bg-white/10 px-3 py-2 text-xs font-semibold text-white hover:bg-white/20"
        >
          <RefreshCw size={13} className={isFetching ? "animate-spin" : undefined} /> Refresh
        </button>
      </div>
      {isLoading ? (
        <div className="flex items-center gap-2 px-5 py-8 text-sm text-[#777]"><RefreshCw size={15} className="animate-spin" /> Loading MailTasks...</div>
      ) : isError ? (
        <div className="flex items-center gap-2 px-5 py-8 text-sm text-[#9a3f38]"><AlertTriangle size={15} /> MailTask queue is temporarily unavailable.</div>
      ) : data.length === 0 ? (
        <div className="px-5 py-8 text-sm text-[#777]">No email-derived tasks are waiting.</div>
      ) : (
        <div>{data.map((task) => <MailTaskRow key={task.id} task={task} canApprove={canApprove} />)}</div>
      )}
      <div className="border-t border-[#d6d6d6] bg-[#fafafa] px-5 py-2.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#888]">Auto refresh 30s · Dashboard is a projection of MailTask records</div>
    </section>
  );
}
