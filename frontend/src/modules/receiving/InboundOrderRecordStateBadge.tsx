import { useI18n } from "../../shared/i18n";

type InboundOrderRecordState = "active" | "archived" | "voided";

interface InboundOrderRecordStateBadgeProps {
  order: {
    archived?: boolean;
    voided?: boolean;
  };
}

export function getInboundOrderRecordState(order: InboundOrderRecordStateBadgeProps["order"]): InboundOrderRecordState {
  if (order.voided) return "voided";
  if (order.archived) return "archived";
  return "active";
}

export default function InboundOrderRecordStateBadge({ order }: InboundOrderRecordStateBadgeProps) {
  const { t } = useI18n();
  const state = getInboundOrderRecordState(order);
  const styles: Record<InboundOrderRecordState, string> = {
    active: "border-[#d7e5d1] bg-[#f4fbf1] text-[#2f6c43]",
    archived: "border-[#d7d0c4] bg-[#f8f4ec] text-[#51606b]",
    voided: "border-[#ebc7c7] bg-[#fff1f1] text-[#8d2f2f]",
  };
  const labels: Record<InboundOrderRecordState, string> = {
    active: t("receiving.recordStateActive", "Active record"),
    archived: t("receiving.recordStateArchived", "Archived record"),
    voided: t("receiving.recordStateVoided", "Voided record"),
  };

  return (
    <span className={`inline-flex shrink-0 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium leading-none ${styles[state]}`}>
      {labels[state]}
    </span>
  );
}
