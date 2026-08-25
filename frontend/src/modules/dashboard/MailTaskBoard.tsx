import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, ChevronDown, ChevronUp, Mail, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useAuthStore } from "../../shared/hooks/useAuth";
import { GreaterWmsTable, GreaterWmsTableCell, GreaterWmsTableHeader, GreaterWmsTableHeaderCell, GreaterWmsTableRow } from "../../shared/components/GreaterWmsTable";
import {
  decideOutboundApproval,
  fetchMailTask,
  fetchMailTasks,
  type MailTaskStatus,
  type MailTaskSummary,
  updateMailTaskStatus,
} from "../../shared/api/mailtasks";
import { queryKeys } from "../../shared/api/queryKeys";
import { isGreaterWmsPreviewMode } from "../../shared/previewMode";

const statusClass: Record<string, string> = {
  "Needs Maggie Processing": "border-[#c8d3e4] bg-[#eef4fc] text-[#345d8e]",
  "Needs Sunny Review": "border-[#e3bd73] bg-[#fff8e8] text-[#99651d]",
  "Awaiting Sunny Approval": "border-[#d69a93] bg-[#fff1ef] text-[#9a3f38]",
  "Ready for WMS": "border-[#9ccfb0] bg-[#edf9f1] text-[#2d7047]",
  "Needs Review": "border-[#d69a93] bg-[#fff1ef] text-[#9a3f38]",
  Blocked: "border-[#d69a93] bg-[#fff1ef] text-[#9a3f38]",
  Executed: "border-[#9ccfb0] bg-[#edf9f1] text-[#2d7047]",
  Closed: "border-[#b7b7b7] bg-[#f5f5f5] text-[#555]",
};

const MAIL_TASK_TABLE_COLUMNS = "152px minmax(270px,1.5fr) minmax(230px,1.25fr) 210px 180px 84px";
const MAIL_TASK_TABLE_MIN_WIDTH = 1120;
const compactStatusLabel: Record<string, string> = {
  "Needs Maggie Processing": "Maggie processing",
  "Needs Sunny Review": "Sunny review",
  "Awaiting Sunny Approval": "Sunny approval",
  "Ready for WMS": "Ready for WMS",
  "Needs Review": "Needs review",
};

function statusLabel(status: string): string {
  return compactStatusLabel[status] || status;
}

function canAdvance(task: MailTaskSummary): MailTaskStatus | null {
  if (task.task_status === "Needs Maggie Processing") return "Needs Sunny Review";
  if (task.task_status === "Needs Sunny Review") return "Awaiting Sunny Approval";
  if (task.task_status === "Ready for WMS") return "WMS In Progress";
  return null;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

const previewMailTasks: MailTaskSummary[] = [
  {
    id: "preview-mailtask-ib",
    task_key: "MT-IB-001",
    business_task_key: "BT-IB-001",
    source_message_key: "preview/message/001",
    subject: "Delta receiving notice · ASN 240824-01",
    title: "Delta receiving notice · ASN 240824-01",
    next_action: "Create inbound order",
    external_reference: "ASN-240824-01",
    record_type: "IB",
    direction: "Inbound",
    task_status: "Needs Maggie Processing",
    task_owner: "Maggie",
    physical_execution_owner: "Mark",
    approval_status: "Not required",
    exception_flag: false,
    wms_system: "LEGACY_PROD",
    wms_doc_no: null,
    linked_message_count: 2,
    latest_message_subject: "Delta receiving notice · ASN 240824-01",
    latest_message_at: "2026-08-24T11:38:00Z",
    latest_source_message_key: "preview/message/001",
  },
  {
    id: "preview-mailtask-ob",
    task_key: "MT-OB-001",
    business_task_key: "BT-OB-001",
    source_message_key: "preview/message/002",
    subject: "Delta outbound instruction · DO-240824-07",
    title: "Delta outbound instruction · DO-240824-07",
    next_action: "Sunny approval",
    external_reference: "DO-240824-07",
    record_type: "OB",
    direction: "Outbound",
    task_status: "Awaiting Sunny Approval",
    task_owner: "Sunny",
    physical_execution_owner: "Mark",
    approval_status: "Pending",
    exception_flag: false,
    wms_system: "LEGACY_PROD",
    wms_doc_no: "DO-240824-07",
    linked_message_count: 2,
    latest_message_subject: "Delta outbound instruction · DO-240824-07",
    latest_message_at: "2026-08-24T11:42:00Z",
    latest_source_message_key: "preview/message/002",
  },
  {
    id: "preview-mailtask-review",
    task_key: "MT-REVIEW-001",
    business_task_key: "BT-REVIEW-001",
    source_message_key: "preview/message/003",
    subject: "BOL revision requires review",
    title: "BOL revision requires review",
    next_action: "Confirm document change",
    external_reference: "BOL-240824-03",
    record_type: "REVIEW",
    direction: "Outbound",
    task_status: "Needs Review",
    task_owner: "Sunny",
    physical_execution_owner: "Mark",
    approval_status: "Review",
    exception_flag: true,
    wms_system: "LEGACY_PROD",
    wms_doc_no: null,
    linked_message_count: 1,
    latest_message_subject: "BOL revision requires review",
    latest_message_at: "2026-08-24T11:44:00Z",
    latest_source_message_key: "preview/message/003",
  },
];

function MailTaskRow({ task, canApprove, rowIndex }: { task: MailTaskSummary; canApprove: boolean; rowIndex: number }) {
  const [expanded, setExpanded] = useState(false);
  const previewMode = isGreaterWmsPreviewMode();
  const queryClient = useQueryClient();
  const detailQuery = useQuery({
    queryKey: queryKeys.mailTasks.detail(task.task_key),
    queryFn: () => fetchMailTask(task.task_key),
    enabled: expanded && !previewMode,
  });
  const statusMutation = useMutation({
    mutationFn: (nextStatus: MailTaskStatus) => updateMailTaskStatus(task.task_key, nextStatus),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.mailTasks.list() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.mailTasks.detail(task.task_key) });
    },
  });
  const approvalMutation = useMutation({
    mutationFn: () => decideOutboundApproval(task.task_key, "approve", "Approved in GreaterWMS Mail2Task"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.mailTasks.list() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.mailTasks.detail(task.task_key) });
    },
  });
  const nextStatus = canAdvance(task);
  const isBusy = statusMutation.isPending || approvalMutation.isPending;
  const badge = statusClass[task.task_status] || "border-[#d0d0d0] bg-[#f7f7f7] text-[#555]";

  return (
    <>
      <GreaterWmsTableRow columns={MAIL_TASK_TABLE_COLUMNS} minWidth={MAIL_TASK_TABLE_MIN_WIDTH} stripe={rowIndex % 2 === 1 ? "alternate" : "base"}>
        <GreaterWmsTableCell className="flex flex-col justify-center">
          <span title={task.task_status} className={`inline-flex w-fit max-w-full border px-2 py-1 text-[10px] font-bold tracking-[0.08em] ${badge}`}>{statusLabel(task.task_status)}</span>
          {task.exception_flag && <span className="mt-2 inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-[0.08em] text-[#c9574f]"><AlertTriangle size={12} /> Exception</span>}
        </GreaterWmsTableCell>
        <GreaterWmsTableCell>
          <div className="flex items-center gap-2"><p className="truncate font-semibold text-[#202020]">{task.title || task.subject || "Business task"}</p><span className="shrink-0 border border-[#9db7d6] bg-[#eef4fc] px-1.5 py-0.5 text-[10px] font-bold text-[#345d8e]">{task.record_type}</span></div>
          <p className="mt-1 truncate font-mono text-[11px] text-[#4d5662]">{task.external_reference || task.business_task_key}</p>
          <p className="mt-1 truncate text-[11px] text-[#858b94]">{task.direction} · Owner {task.task_owner || "Unassigned"}</p>
        </GreaterWmsTableCell>
        <GreaterWmsTableCell>
          <p className="font-semibold text-[#252525]">{task.next_action || "Review task details"}</p>
          <p className="mt-1 text-[11px] text-[#777]">Physical: {task.physical_execution_owner || "Unassigned"}</p>
          <p className="mt-1 text-[11px] text-[#777]">Approval: {task.approval_status}</p>
        </GreaterWmsTableCell>
        <GreaterWmsTableCell>
          <p className="flex items-center gap-1.5 font-semibold text-[#252525]"><Mail size={13} className="text-[#5d6b8b]" /> {task.linked_message_count} email{task.linked_message_count === 1 ? "" : "s"}</p>
          <p className="mt-1 truncate text-[11px] text-[#555]" title={task.latest_message_subject}>{task.latest_message_subject}</p>
          <p className="mt-1 font-mono text-[10px] text-[#888]">Latest {formatDate(task.latest_message_at)}</p>
        </GreaterWmsTableCell>
        <GreaterWmsTableCell className="text-xs text-[#4d5662]">{task.wms_doc_no ? <><p className="font-semibold">{task.wms_system || "WMS"}</p><p className="mt-1 font-mono">{task.wms_doc_no}</p></> : <p>WMS reference pending</p>}</GreaterWmsTableCell>
        <GreaterWmsTableCell className="flex items-center justify-center px-2"><button type="button" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded} className="inline-flex items-center gap-1 border border-[#9aa4bb] bg-white px-2 py-2 text-[11px] font-semibold text-[#4c5d82] hover:border-[#5d6b8b] hover:bg-[#5d6b8b] hover:text-white">{expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />} Detail</button></GreaterWmsTableCell>
      </GreaterWmsTableRow>

      <div className="border-t border-[#dedede] bg-white px-3 py-3 text-[12px] sm:hidden">
        <div className="flex items-start justify-between gap-3"><div className="min-w-0"><span title={task.task_status} className={`inline-flex border px-2 py-1 text-[10px] font-bold tracking-[0.08em] ${badge}`}>{statusLabel(task.task_status)}</span><p className="mt-2 truncate font-semibold text-[#202020]">{task.title || task.subject || "Business task"}</p><p className="truncate font-mono text-[10px] text-[#777]">{task.external_reference || task.business_task_key}</p></div><button type="button" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded} className="shrink-0 border border-[#9aa4bb] bg-white p-2 text-[#4c5d82]">{expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</button></div>
        <div className="mt-3 grid grid-cols-2 gap-2 border-t border-[#eeeeee] pt-2 text-[11px] text-[#555]"><span>Next: <strong className="text-[#252525]">{task.next_action || "Review task details"}</strong></span><span>Owner: <strong className="text-[#252525]">{task.task_owner || "Unassigned"}</strong></span><span className="flex items-center gap-1"><Mail size={12} /> {task.linked_message_count} email{task.linked_message_count === 1 ? "" : "s"}</span><span>Latest: {formatDate(task.latest_message_at)}</span></div>
      </div>

      {expanded && <div className="border-t border-[#d7dbe2] bg-[#f7f8fa] px-4 py-4 sm:col-span-6 sm:px-5"><div className="grid gap-4 lg:grid-cols-[minmax(220px,0.8fr)_minmax(0,1.8fr)_auto]"><div><p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-[#747d89]">Business task</p><p className="mt-1 break-all font-mono text-[11px] text-[#303b5b]">{task.business_task_key}</p><p className="mt-2 text-xs text-[#555]">Latest source: <span className="font-mono">{task.latest_source_message_key || "--"}</span></p></div><div><p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-[#747d89]">Email evidence timeline</p>{detailQuery.isLoading ? <p className="mt-2 text-xs text-[#777]">Loading linked emails...</p> : detailQuery.isError ? <p className="mt-2 text-xs text-[#9a3f38]">Email evidence unavailable.</p> : detailQuery.data?.messages.length ? <div className="mt-2 space-y-2">{detailQuery.data.messages.map((message) => <div key={message.source_message_key} className="border border-[#d7dbe2] bg-white px-3 py-2"><div className="flex flex-wrap items-center justify-between gap-2"><p className="truncate text-xs font-semibold text-[#252525]">{message.subject || "(no subject)"}</p><span className="font-mono text-[10px] text-[#888]">{formatDate(message.received_at)}</span></div><p className="mt-1 truncate font-mono text-[10px] text-[#697382]">{message.source_message_key} · {message.sender}</p></div>)}</div> : <p className="mt-2 text-xs text-[#777]">No linked email evidence.</p>}</div><div className="flex flex-wrap items-start gap-2 lg:justify-end">{task.task_status === "Awaiting Sunny Approval" && canApprove && <button type="button" disabled={isBusy} onClick={() => approvalMutation.mutate()} className="inline-flex items-center gap-1 border border-[#5d936d] bg-[#edf9f1] px-3 py-2 text-xs font-semibold text-[#2d7047] hover:bg-[#dff2e5] disabled:opacity-50"><Check size={13} /> Approve OB</button>}{nextStatus && <button type="button" disabled={isBusy} onClick={() => statusMutation.mutate(nextStatus)} className="border border-[#9aa4bb] bg-white px-3 py-2 text-xs font-semibold text-[#4c5d82] hover:border-[#5d6b8b] hover:bg-[#5d6b8b] hover:text-white disabled:opacity-50">{nextStatus === "WMS In Progress" ? "Start WMS" : nextStatus}</button>}</div></div></div>}
    </>
  );
}

export default function MailTaskBoard() {
  const permissions = useAuthStore((state) => state.permissions);
  const canView = permissions.includes("*") || permissions.includes("mailtask.execute") || permissions.includes("mailtask.manage");
  const canApprove = permissions.includes("*") || permissions.includes("mailtask.approve_outbound");
  const previewMode = isGreaterWmsPreviewMode();
  const { data: fetchedData = [], isLoading: fetchedLoading, isError, isFetching, refetch } = useQuery({ queryKey: queryKeys.mailTasks.list(), queryFn: () => fetchMailTasks({ limit: 100 }), enabled: canView && !previewMode, refetchInterval: canView && !previewMode ? 30_000 : false });
  const data = previewMode ? previewMailTasks : fetchedData;
  const isLoading = !previewMode && fetchedLoading;
  const exceptionCount = data.filter((task) => task.exception_flag).length;
  const pendingCount = data.filter((task) => task.task_status === "Needs Maggie Processing").length;

  if (!canView) return null;

  return (
    <section className="w-full rounded-[2px] border border-[#d7d7d7] bg-white shadow-[0_4px_14px_rgba(0,0,0,0.22)]" data-testid="mailtask-board" aria-label="Mail2Task business task work queue">
      <div className="flex min-h-12 items-center gap-3 bg-[#596782] px-3 text-white sm:px-4">
        <h2 className="text-[16px] font-bold uppercase tracking-[0.08em]">Mail to Task</h2>
        <div className="ml-auto flex items-center gap-3 text-[11px] font-bold uppercase">
          <span className="text-[#f1cf74]">{isError ? "STAGED" : "LIVE"}</span>
          <button type="button" aria-label="Refresh mail tasks" onClick={() => void refetch()} className="inline-flex h-7 w-7 items-center justify-center hover:bg-white/10"><RefreshCw size={16} className={isFetching ? "animate-spin" : undefined} /></button>
        </div>
      </div>
      <div className="flex min-h-10 items-center border-b border-[#dfe3ea] px-3 text-[12px] sm:px-4">
        <span className="text-[#667085]">Incoming email work queue</span>
        <div className="ml-auto flex items-center gap-3 text-[11px] font-bold uppercase"><span className="text-[#667085]">Open {data.length}</span><span className="text-[#b54708]">Due {pendingCount}</span><span className="text-[#b42318]">Review {exceptionCount}</span></div>
      </div>
      <div className="flex min-h-10 items-center border-b border-[#dfe3ea] bg-[#f5f6f8] px-3 sm:px-4">
        <span className="border-b-[3px] border-[#1976d2] px-3 py-2.5 text-[14px] font-semibold uppercase text-[#1976d2]">All</span>
        <span className="px-3 py-2.5 text-[14px] font-semibold uppercase text-[#333]">IB</span>
        <span className="px-3 py-2.5 text-[14px] font-semibold uppercase text-[#333]">OB</span>
        <span className="px-3 py-2.5 text-[14px] font-semibold uppercase text-[#333]">Review</span>
        <span className="ml-auto border border-[#1976d2] px-2 py-1 text-[10px] font-semibold text-[#1976d2]">PS MAIL</span>
      </div>
      {isLoading ? <div className="flex items-center gap-3 px-6 py-12 text-sm text-[#777]"><RefreshCw size={16} className="animate-spin" /> Loading business task queue...</div> : isError ? <div className="flex items-center gap-3 px-6 py-12 text-sm text-[#9a3f38]"><AlertTriangle size={17} /> Mail2Task queue is temporarily unavailable.</div> : data.length === 0 ? <div className="px-6 py-12 text-sm text-[#777]">No email-derived business tasks are waiting.</div> : <GreaterWmsTable>
        <GreaterWmsTableHeader columns={MAIL_TASK_TABLE_COLUMNS} minWidth={MAIL_TASK_TABLE_MIN_WIDTH}>
          <GreaterWmsTableHeaderCell>Status</GreaterWmsTableHeaderCell>
          <GreaterWmsTableHeaderCell>Business task / ref</GreaterWmsTableHeaderCell>
          <GreaterWmsTableHeaderCell>Pending action / owner</GreaterWmsTableHeaderCell>
          <GreaterWmsTableHeaderCell>Mail evidence</GreaterWmsTableHeaderCell>
          <GreaterWmsTableHeaderCell>WMS handoff</GreaterWmsTableHeaderCell>
          <GreaterWmsTableHeaderCell>Open</GreaterWmsTableHeaderCell>
        </GreaterWmsTableHeader>
        {data.map((task, rowIndex) => <MailTaskRow key={task.id} task={task} canApprove={canApprove} rowIndex={rowIndex} />)}
      </GreaterWmsTable>}
      <div className="border-t border-[#d6d6d6] bg-[#fafafa] px-4 py-2.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#888] sm:px-5">Auto refresh 30s · Mail2Task is the email-to-task workbench; Warehouse Operations remains the execution board</div>
    </section>
  );
}
