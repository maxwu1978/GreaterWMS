import api from "./client";

export type MailTaskStatus =
  | "New"
  | "Extracted"
  | "Needs Maggie Processing"
  | "Needs Sunny Review"
  | "Awaiting Sunny Approval"
  | "Needs Customer Confirmation"
  | "Needs Field Completion"
  | "Ready for WMS"
  | "WMS In Progress"
  | "Executed"
  | "Awaiting POD"
  | "Closed"
  | "Needs Review"
  | "Blocked"
  | "Excluded";

export type MailTaskSummary = {
  id: string;
  task_key: string;
  source_message_key: string;
  subject: string;
  record_type: string;
  direction: string;
  task_status: MailTaskStatus;
  task_owner?: string | null;
  physical_execution_owner?: string | null;
  approval_status: string;
  exception_flag: boolean;
  wms_system?: string | null;
  wms_doc_no?: string | null;
};

export function fetchMailTasks(params?: {
  status?: MailTaskStatus;
  direction?: string;
  task_owner?: string;
  limit?: number;
}): Promise<MailTaskSummary[]> {
  return api.get("/mailtasks/", { params }).then((response) => response.data);
}

export function updateMailTaskStatus(
  taskKey: string,
  taskStatus: MailTaskStatus,
): Promise<MailTaskSummary> {
  return api.patch(`/mailtasks/${encodeURIComponent(taskKey)}/status`, {
    TaskStatus: taskStatus,
  }).then((response) => response.data);
}

export function decideOutboundApproval(
  taskKey: string,
  decision: "approve" | "reject",
  note?: string,
): Promise<MailTaskSummary> {
  return api.post(`/mailtasks/${encodeURIComponent(taskKey)}/outbound-approval`, {
    decision,
    note,
  }).then((response) => response.data);
}
