/**
 * Scan step: already-received lines panel.
 * JSX moved verbatim from ReceivingFlow.tsx — no behavior change.
 */

import StatusBadge from "../../../shared/components/StatusBadge";
import { type ReceivedLine } from "../receivingFlowUtils";

type Translator = (key: string, fallback?: string, vars?: Record<string, string | number>) => string;

interface ReceivedLinesPanelProps {
  t: Translator;
  receivedLines: ReceivedLine[];
  hasActiveLabel: boolean;
}

export default function ReceivedLinesPanel({ t, receivedLines, hasActiveLabel }: ReceivedLinesPanelProps) {
  if (receivedLines.length === 0) return null;
  return (
          <div id="receiving-received-lines" className={`rounded-lg bg-white p-4 shadow ${hasActiveLabel ? "hidden md:block" : ""}`}>
            <h3 className="text-sm font-medium text-gray-700 mb-2">
              {t("receivingFlow.receivedLines", "Received ({count} packages)", {
                count: receivedLines.length,
              })}
            </h3>
            <div className="hidden md:block">
              {receivedLines.map((line, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0"
                >
                  <span className="text-sm">{line.sku_id}</span>
                  <div className="flex items-center gap-3 text-sm">
                    {line.package_number ? (
                      <span className="rounded-full bg-[#fcfaf5] px-2 py-1 text-xs font-medium text-[#51606b]">
                        {t("receivingFlow.packageCardTitle", "Package {number}", {
                          number: line.package_number,
                        })}
                      </span>
                    ) : null}
                    {line.label_code ? (
                      <span className="rounded-full bg-[#eef3f6] px-2 py-1 text-xs font-medium text-[#13212c]">
                        {line.label_code}
                      </span>
                    ) : null}
                    <span>
                      {t("receivingFlow.expectedShort", "Exp:")} {line.expected}
                    </span>
                    <span className="font-medium">
                      {t("receivingFlow.receivedShort", "Rcvd:")} {line.received}
                    </span>
                    {line.damaged > 0 && (
                      <span className="text-red-500">
                        {t("receivingFlow.damagedShort", "Dmg:")} {line.damaged}
                      </span>
                    )}
                    {line.discrepancy_qty ? (
                      <span className={line.discrepancy_qty > 0 ? "text-amber-600" : "text-blue-600"}>
                        {line.discrepancy_qty > 0
                          ? t("receivingFlow.overShort", "Over: {count}", { count: line.discrepancy_qty })
                          : t("receivingFlow.shortShort", "Short: {count}", {
                              count: Math.abs(line.discrepancy_qty),
                            })}
                      </span>
                    ) : null}
                    <StatusBadge status={line.status} />
                  </div>
                </div>
              ))}
            </div>
            <details className="rounded-2xl border border-[#e3ddd2] bg-[#fcfaf5] p-3 md:hidden">
              <summary className="cursor-pointer list-none text-sm font-semibold text-[#13212c]">
                {t("receivingFlow.mobileReceivedToggle", "Show received packages")}
              </summary>
              <div className="mt-3 space-y-3">
                {receivedLines.map((line, i) => (
                  <div key={i} className="rounded-2xl border border-[#e3ddd2] bg-white p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[#13212c]">{line.sku_id}</p>
                        <p className="mt-1 text-xs text-[#61717d]">
                          {line.package_number
                            ? t("receivingFlow.packageCardTitle", "Package {number}", {
                                number: line.package_number,
                              })
                            : t("receivingFlow.receivedLines", "Received ({count} lines)", { count: 1 })}
                          {line.label_code ? ` · ${line.label_code}` : ""}
                        </p>
                      </div>
                      <StatusBadge status={line.status} />
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-[#51606b]">
                      <span>{t("receivingFlow.expectedShort", "Exp:")} {line.expected}</span>
                      <span>{t("receivingFlow.receivedShort", "Rcvd:")} {line.received}</span>
                      {line.damaged > 0 ? (
                        <span className="text-red-500">
                          {t("receivingFlow.damagedShort", "Dmg:")} {line.damaged}
                        </span>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </details>
          </div>
  );
}
