import { Link, useNavigate } from "react-router-dom";
import { useI18n } from "../../shared/i18n";

function packageOriginLabel(
  origin: string | null | undefined,
  t: (key: string, fallback: string, vars?: Record<string, string | number>) => string,
) {
  if (origin === "dock_created") return t("receiving.packageOriginDockCreated", "Opened at dock");
  return t("receiving.packageOriginPrebooked", "Pre-booked");
}

function DownstreamMetric({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <div className="rounded-[1rem] border border-[#13212c]/8 bg-white px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">{label}</p>
      <p className="mt-2 text-base font-semibold text-[#13212c]">{value}</p>
      <p className="mt-1.5 text-sm leading-6 text-[#61717d]">{detail}</p>
    </div>
  );
}

export default function InboundOrderDownstreamPanel({
  detail,
  orderId,
  orderNumber,
  referenceNumber,
}: {
  detail: any;
  orderId?: string | null;
  orderNumber?: string | null;
  referenceNumber?: string | null;
}) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const summary = detail?.downstream_summary || {};
  const lines = detail?.lines || [];

  const persistPutawayFocus = (payload: Record<string, string | null | undefined>) => {
    if (typeof window === "undefined") return;
    window.sessionStorage.setItem(
      "putaway.focusContext",
      JSON.stringify({
        source: "inbound-detail",
        orderId: orderId || null,
        orderNumber: orderNumber || null,
        referenceNumber: referenceNumber || null,
        ...payload,
      }),
    );
  };

  const persistReceivingFocus = (payload: {
    packageId: string;
    packageNumber?: number | null;
    target: "package" | "print";
  }) => {
    if (typeof window === "undefined" || !orderId) return;
    window.sessionStorage.setItem("receiving.selectedOrderId", orderId);
    window.sessionStorage.setItem(
      "receiving.focusContext",
      JSON.stringify({
        orderId,
        packageId: payload.packageId,
        packageNumber: payload.packageNumber || null,
        target: payload.target,
      }),
    );
    navigate("/receiving");
  };

  return (
    <section className="rounded-[1.6rem] border border-[#13212c]/10 bg-white/90 p-5 shadow-[0_18px_44px_rgba(19,33,44,0.06)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-[#7f8d98]">
            {t("receiving.detailDownstreamEyebrow", "Downstream visibility")}
          </p>
          <h2 className="mt-2 text-lg font-semibold text-[#13212c]">
            {t("receiving.detailDownstreamTitle", "Track handling units and putaway work after dock confirmation")}
          </h2>
        </div>
        {((summary.putaway_tasks_pending || 0) + (summary.putaway_tasks_in_progress || 0)) > 0 ? (
          <Link
            to="/putaway"
            onClick={() => {
              if (!orderNumber) return;
              persistPutawayFocus({});
            }}
            className="inline-flex items-center gap-2 rounded-full border border-[#13212c]/10 bg-white px-4 py-2 text-sm font-semibold text-[#13212c]"
          >
            {t("receiving.detailOpenPutawayAction", "Open putaway board")}
          </Link>
        ) : null}
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <DownstreamMetric
          label={t("receiving.detailPutawayTasksTotal", "Putaway tasks")}
          value={summary.putaway_tasks_total || 0}
          detail={t("receiving.detailPutawayTasksTotalBody", "Total downstream tasks created from this inbound order.")}
        />
        <DownstreamMetric
          label={t("receiving.detailPutawayTasksOpen", "Open putaway work")}
          value={(summary.putaway_tasks_pending || 0) + (summary.putaway_tasks_in_progress || 0)}
          detail={t("receiving.detailPutawayTasksOpenBody", "Pending or in-progress downstream work that still needs warehouse action.")}
        />
        <DownstreamMetric
          label={t("receiving.detailPutawayPendingUnits", "Units awaiting putaway")}
          value={summary.handling_units_putaway_pending || 0}
          detail={t("receiving.detailPutawayPendingUnitsBody", "Handling units that have left dock confirmation but have not reached final storage yet.")}
        />
        <DownstreamMetric
          label={t("receiving.detailStoredUnits", "Units in final storage")}
          value={summary.handling_units_in_final_storage || 0}
          detail={t("receiving.detailStoredUnitsBody", "Handling units already marked as stored after downstream completion.")}
        />
      </div>

      <div className="mt-5 space-y-3">
        {lines.map((line: any) => (
          <div key={line.line_id} className="rounded-[1.2rem] border border-[#13212c]/8 bg-[#faf7f2] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-[#13212c]">
                  {line.sku_code} {line.sku_name ? `· ${line.sku_name}` : ""}
                </p>
                <p className="mt-1 text-sm text-[#61717d]">
                  {line.staging_location_barcode
                    ? t("receiving.detailDownstreamLineBody", "Staged at {location}. Follow each handling unit into putaway from here.", {
                        location: line.staging_location_barcode,
                      })
                    : t("receiving.detailDownstreamLineBodyNoStage", "Follow each handling unit and downstream task from this line.")}
                </p>
              </div>
            </div>

            {line.packages?.length ? (
              <div className="mt-3 space-y-3">
                {line.packages.map((pkg: any) => (
                  <div key={pkg.id} className="rounded-[1rem] border border-[#13212c]/8 bg-white px-4 py-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[#13212c]">
                          {t("receiving.packageTitle", "Package {number}", { number: String(pkg.package_number || 1) })}
                        </p>
                        <p className="mt-1 text-sm text-[#61717d]">
                          {pkg.staging_location_barcode
                            ? t(
                                "receiving.detailDownstreamPackageBody",
                                "This package was staged at {location} and can now be followed through downstream work.",
                                { location: pkg.staging_location_barcode },
                              )
                            : t("receiving.detailDownstreamPackageBodyNoStage", "Follow this package through handling and putaway from here.")}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-[11px] font-medium text-[#51606b]">
                          {packageOriginLabel(pkg.package_origin, t)}
                        </span>
                        <span className="rounded-full bg-[#edf2f7] px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#51606b]">
                          {pkg.status || "—"}
                        </span>
                        {pkg.label_sequence ? (
                          <span className="rounded-full border border-[#d7d0c4] bg-white px-3 py-1 text-[11px] font-medium text-[#51606b]">
                            {t("receiving.detailPackageInternalSlot", "Internal slot {sequence}", {
                              sequence: String(pkg.label_sequence),
                            })}
                          </span>
                        ) : null}
                      </div>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2">
                      {!["received", "staged", "putaway_pending", "stored"].includes(pkg.status || "") ? (
                        <button
                          type="button"
                          onClick={() =>
                            persistReceivingFocus({
                              packageId: pkg.id,
                              packageNumber: pkg.package_number,
                              target: "package",
                            })
                          }
                          className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                        >
                          {t("receiving.detailOpenPackageInReceivingAction", "Open package in receiving")}
                        </button>
                      ) : null}
                      {(pkg.receiving_labels || []).some((label: any) => (label.print_count || 0) === 0) ? (
                        <button
                          type="button"
                          onClick={() =>
                            persistReceivingFocus({
                              packageId: pkg.id,
                              packageNumber: pkg.package_number,
                              target: "print",
                            })
                          }
                          className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                        >
                          {t("receiving.detailOpenPackagePrintAction", "Open package print")}
                        </button>
                      ) : null}
                    </div>

                    <div className="mt-3 grid gap-3 xl:grid-cols-2">
                      <div className="rounded-[0.9rem] border border-[#13212c]/8 bg-[#faf7f2] px-3 py-3">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                          {t("receiving.detailHandlingUnits", "Handling units")}
                        </p>
                        <div className="mt-3 space-y-3">
                          {pkg.handling_units?.length ? (
                            pkg.handling_units.map((unit: any) => (
                              <div key={unit.id} className="rounded-[0.9rem] border border-[#13212c]/8 bg-white px-3 py-3">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <p className="text-sm font-semibold text-[#13212c]">{unit.unit_code}</p>
                                  <div className="flex flex-wrap items-center gap-2">
                                    {unit.unit_code &&
                                    pkg.downstream_tasks?.some(
                                      (task: any) => task.handling_unit_code === unit.unit_code && task.status !== "completed",
                                    ) ? (
                                      <Link
                                        to="/putaway"
                                        onClick={() => persistPutawayFocus({ handlingUnitCode: unit.unit_code })}
                                        className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                                      >
                                        {t("receiving.detailOpenUnitInPutawayAction", "Open unit")}
                                      </Link>
                                    ) : null}
                                    <span className="rounded-full bg-[#edf2f7] px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#51606b]">
                                      {unit.status || "—"}
                                    </span>
                                  </div>
                                </div>
                                <div className="mt-2 flex flex-wrap gap-2 text-xs text-[#61717d]">
                                  {unit.package_count != null ? (
                                    <span className="rounded-full bg-[#faf7f2] px-2.5 py-1">
                                      {t("receiving.detailPackagesShort", "Packages")} {unit.package_count}
                                    </span>
                                  ) : null}
                                  {unit.pallet_count != null ? (
                                    <span className="rounded-full bg-[#faf7f2] px-2.5 py-1">
                                      {t("receiving.detailPalletsShort", "Pallets")} {unit.pallet_count}
                                    </span>
                                  ) : null}
                                  {unit.staging_location_barcode ? (
                                    <span className="rounded-full bg-[#faf7f2] px-2.5 py-1">
                                      {t("receiving.orderHistoryStaging", "Staging")} {unit.staging_location_barcode}
                                    </span>
                                  ) : null}
                                </div>
                              </div>
                            ))
                          ) : (
                            <p className="text-sm text-[#7f8d98]">
                              {t("receiving.detailNoHandlingUnits", "No confirmed handling units have been issued from this line yet.")}
                            </p>
                          )}
                        </div>
                      </div>

                      <div className="rounded-[0.9rem] border border-[#13212c]/8 bg-[#faf7f2] px-3 py-3">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                          {t("receiving.detailDownstreamTasks", "Downstream tasks")}
                        </p>
                        <div className="mt-3 space-y-3">
                          {pkg.downstream_tasks?.length ? (
                            pkg.downstream_tasks.map((task: any) => (
                              <div key={task.id} className="rounded-[0.9rem] border border-[#13212c]/8 bg-white px-3 py-3">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <p className="text-sm font-semibold text-[#13212c]">
                                    {task.handling_unit_code || t("receiving.detailTaskWithoutUnit", "Putaway task")}
                                  </p>
                                  <div className="flex flex-wrap items-center gap-2">
                                    {(task.id || task.handling_unit_code) && task.status !== "completed" ? (
                                      <Link
                                        to="/putaway"
                                        onClick={() =>
                                          persistPutawayFocus({
                                            taskId: task.id || null,
                                            handlingUnitCode: task.handling_unit_code || null,
                                          })
                                        }
                                        className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                                      >
                                        {t("receiving.detailOpenTaskInPutawayAction", "Open task")}
                                      </Link>
                                    ) : null}
                                    <span className="rounded-full bg-[#edf2f7] px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#51606b]">
                                      {task.status || "—"}
                                    </span>
                                  </div>
                                </div>
                                <p className="mt-2 text-sm text-[#61717d]">
                                  {task.source_location_barcode || "—"} → {task.destination_location_barcode || t("receiving.detailDestinationPending", "destination pending")}
                                </p>
                              </div>
                            ))
                          ) : (
                            <p className="text-sm text-[#7f8d98]">
                              {t("receiving.detailNoDownstreamTasks", "No downstream putaway tasks are attached to this line yet.")}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-3 grid gap-3 xl:grid-cols-2">
                <div className="rounded-[1rem] border border-[#13212c]/8 bg-white px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                    {t("receiving.detailHandlingUnits", "Handling units")}
                  </p>
                  <div className="mt-3 space-y-3">
                    {line.handling_units?.length ? (
                      line.handling_units.map((unit: any) => (
                        <div key={unit.id} className="rounded-[0.9rem] border border-[#13212c]/8 bg-[#faf7f2] px-3 py-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-sm font-semibold text-[#13212c]">{unit.unit_code}</p>
                            <div className="flex flex-wrap items-center gap-2">
                              {unit.unit_code &&
                              line.downstream_tasks?.some(
                                (task: any) => task.handling_unit_code === unit.unit_code && task.status !== "completed",
                              ) ? (
                                <Link
                                  to="/putaway"
                                  onClick={() => persistPutawayFocus({ handlingUnitCode: unit.unit_code })}
                                  className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                                >
                                  {t("receiving.detailOpenUnitInPutawayAction", "Open unit")}
                                </Link>
                              ) : null}
                              <span className="rounded-full bg-[#edf2f7] px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#51606b]">
                                {unit.status || "—"}
                              </span>
                            </div>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-2 text-xs text-[#61717d]">
                            {unit.package_count != null ? (
                              <span className="rounded-full bg-white px-2.5 py-1">
                                {t("receiving.detailPackagesShort", "Packages")} {unit.package_count}
                              </span>
                            ) : null}
                            {unit.pallet_count != null ? (
                              <span className="rounded-full bg-white px-2.5 py-1">
                                {t("receiving.detailPalletsShort", "Pallets")} {unit.pallet_count}
                              </span>
                            ) : null}
                            {unit.staging_location_id ? (
                              <span className="rounded-full bg-white px-2.5 py-1">
                                {t("receiving.orderHistoryStaging", "Staging")} {unit.staging_location_id}
                              </span>
                            ) : null}
                          </div>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-[#7f8d98]">
                        {t("receiving.detailNoHandlingUnits", "No confirmed handling units have been issued from this line yet.")}
                      </p>
                    )}
                  </div>
                </div>

                <div className="rounded-[1rem] border border-[#13212c]/8 bg-white px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-[#7f8d98]">
                    {t("receiving.detailDownstreamTasks", "Downstream tasks")}
                  </p>
                  <div className="mt-3 space-y-3">
                    {line.downstream_tasks?.length ? (
                      line.downstream_tasks.map((task: any) => (
                        <div key={task.id} className="rounded-[0.9rem] border border-[#13212c]/8 bg-[#faf7f2] px-3 py-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-sm font-semibold text-[#13212c]">
                              {task.handling_unit_code || t("receiving.detailTaskWithoutUnit", "Putaway task")}
                            </p>
                            <div className="flex flex-wrap items-center gap-2">
                              {(task.id || task.handling_unit_code) && task.status !== "completed" ? (
                                <Link
                                  to="/putaway"
                                  onClick={() =>
                                    persistPutawayFocus({
                                      taskId: task.id || null,
                                      handlingUnitCode: task.handling_unit_code || null,
                                    })
                                  }
                                  className="rounded-full border border-[#13212c]/10 bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#13212c]"
                                >
                                  {t("receiving.detailOpenTaskInPutawayAction", "Open task")}
                                </Link>
                              ) : null}
                              <span className="rounded-full bg-[#edf2f7] px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#51606b]">
                                {task.status || "—"}
                              </span>
                            </div>
                          </div>
                          <p className="mt-2 text-sm text-[#61717d]">
                            {task.source_location_barcode || "—"} → {task.destination_location_barcode || t("receiving.detailDestinationPending", "destination pending")}
                          </p>
                          <div className="mt-2 flex flex-wrap gap-2 text-xs text-[#61717d]">
                            <span className="rounded-full bg-white px-2.5 py-1">
                              {t("receiving.detailExecutionMode", "Execution")} {task.execution_mode || "—"}
                            </span>
                            {task.created_at ? (
                              <span className="rounded-full bg-white px-2.5 py-1">
                                {t("receiving.detailTaskCreated", "Created")} {task.created_at}
                              </span>
                            ) : null}
                            {task.completed_at ? (
                              <span className="rounded-full bg-white px-2.5 py-1">
                                {t("receiving.detailTaskCompleted", "Completed")} {task.completed_at}
                              </span>
                            ) : null}
                          </div>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-[#7f8d98]">
                        {t("receiving.detailNoDownstreamTasks", "No downstream putaway tasks are attached to this line yet.")}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
