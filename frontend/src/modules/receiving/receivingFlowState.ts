/**
 * Local reducer state for the interactive receiving workflow.
 *
 * Collapses the former packageEditor* / correction* useState groups from
 * ReceivingFlow.tsx into two reducers. Actions are partial-state patches so
 * each former setX(value) call maps 1:1 to dispatch({ x: value }), and a
 * dispatch of the full initial state is a reset. No behavior change.
 */

export interface PackageEditorState {
  mode: "create" | "edit" | null;
  packageId: string;
  lineId: string;
  expectedQty: string;
  type: string;
  tracking: string;
  carton: string;
  customerCode: string;
  error: string;
}

export const initialPackageEditorState: PackageEditorState = {
  mode: null,
  packageId: "",
  lineId: "",
  expectedQty: "",
  type: "carton",
  tracking: "",
  carton: "",
  customerCode: "",
  error: "",
};

export type PackageEditorAction = Partial<PackageEditorState>;

export function packageEditorReducer(
  state: PackageEditorState,
  action: PackageEditorAction,
): PackageEditorState {
  return { ...state, ...action };
}

export interface CorrectionState {
  packageId: string;
  receivedQty: string;
  damagedQty: string;
  stagingLocation: string;
  packageCount: string;
  palletCount: string;
  rentFreeDays: string;
  weightKg: string;
  lengthCm: string;
  widthCm: string;
  heightCm: string;
  note: string;
  tracking: string;
  carton: string;
  customerCode: string;
  error: string;
}

export const initialCorrectionState: CorrectionState = {
  packageId: "",
  receivedQty: "",
  damagedQty: "",
  stagingLocation: "",
  packageCount: "",
  palletCount: "",
  rentFreeDays: "",
  weightKg: "",
  lengthCm: "",
  widthCm: "",
  heightCm: "",
  note: "",
  tracking: "",
  carton: "",
  customerCode: "",
  error: "",
};

export type CorrectionAction = Partial<CorrectionState>;

export function correctionReducer(state: CorrectionState, action: CorrectionAction): CorrectionState {
  return { ...state, ...action };
}
