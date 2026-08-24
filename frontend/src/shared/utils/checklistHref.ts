/**
 * Maps a setup-checklist step name to its deep link on the /setup page.
 */
export function checklistHref(stepName: string) {
  switch (stepName) {
    case "warehouse":
      return "/setup?step=warehouse";
    case "locations":
      return "/setup?step=locations";
    case "client":
      return "/setup?step=client";
    case "skus":
      return "/setup?step=skus";
    case "billing":
      return "/setup?step=billing";
    case "team":
      return "/setup?step=team";
    default:
      return "/setup";
  }
}
