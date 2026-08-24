/**
 * Data layer for the interactive receiving workflow.
 *
 * Wraps every react-query read that ReceivingFlow consumes. Moved verbatim
 * from ReceivingFlow.tsx — no behavior change.
 */

import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "../../shared/api/queryKeys";
import {
  fetchInboundOrderDetail,
  fetchObservedReceivingCodes,
  fetchReceivableInboundOrders,
  fetchReceivingLabelTemplate,
  fetchReceivingLabels,
  fetchReceivingPackages,
  fetchReceivingStagingLocations,
} from "../../shared/api/receiving";
import {
  type InboundDetailSummary,
  type InboundPackageSummary,
  type InboundReceivableOrder,
  type ObservedReceivingCode,
  type ReceivingLabelSummary,
  type ReceivingLabelTemplateSettings,
  type ScannedReceivingLabel,
} from "./receivingFlowUtils";

export function useReceivingFlowData({
  orderId,
  scannedLabel,
}: {
  orderId: string;
  scannedLabel: ScannedReceivingLabel | null;
}) {
  // Load orders in "expected" or "receiving" status
  const { data: orders = [] } = useQuery<InboundReceivableOrder[]>({
    queryKey: queryKeys.inboundOrders.receivable(),
    queryFn: fetchReceivableInboundOrders,
  });
  const selectedOrder = orders.find((order) => order.id === orderId);

  const { data: stagingLocations = [] } = useQuery({
    queryKey: queryKeys.receiving.stagingLocations(selectedOrder?.warehouse_id),
    enabled: !!selectedOrder?.warehouse_id,
    queryFn: () => {
      if (!selectedOrder?.warehouse_id) {
        return Promise.resolve([]);
      }
      return fetchReceivingStagingLocations(selectedOrder.warehouse_id);
    },
  });

  const { data: receivingLabels = [], isLoading: isLoadingReceivingLabels } = useQuery<ReceivingLabelSummary[]>({
    queryKey: queryKeys.receiving.labels(orderId),
    enabled: !!orderId,
    queryFn: () => fetchReceivingLabels(orderId),
  });

  const { data: packages = [], isLoading: isLoadingPackages } = useQuery<InboundPackageSummary[]>({
    queryKey: queryKeys.receiving.packages(orderId),
    enabled: !!orderId,
    queryFn: () => fetchReceivingPackages(orderId),
  });

  const { data: orderDetail } = useQuery<InboundDetailSummary>({
    queryKey: queryKeys.inboundOrders.detail(orderId),
    enabled: !!orderId,
    queryFn: () => fetchInboundOrderDetail(orderId),
  });

  const { data: labelTemplateSettings } = useQuery<ReceivingLabelTemplateSettings>({
    queryKey: queryKeys.receiving.labelTemplate(),
    queryFn: fetchReceivingLabelTemplate,
  });

  const { data: observedCodes = [] } = useQuery<ObservedReceivingCode[]>({
    queryKey: queryKeys.receiving.observedCodes(orderId, scannedLabel?.package_id || scannedLabel?.label_code),
    enabled: !!orderId && (!!scannedLabel?.package_id || !!scannedLabel?.label_code),
    queryFn: () =>
      fetchObservedReceivingCodes(
        orderId,
        scannedLabel?.package_id
          ? { package_id: scannedLabel.package_id }
          : { label_code: scannedLabel?.label_code },
      ),
  });

  return {
    orders,
    selectedOrder,
    stagingLocations,
    receivingLabels,
    isLoadingReceivingLabels,
    packages,
    isLoadingPackages,
    orderDetail,
    labelTemplateSettings,
    observedCodes,
  };
}
