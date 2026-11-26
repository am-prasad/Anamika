/** Three evidence groups, three validated categorical slots (series-1, -3, -4 on #0A1424). */
export type EvidenceGroup = "id" | "contact" | "name";

export const EVIDENCE_COLOR: Record<EvidenceGroup, string> = {
  id: "#3987E5",
  contact: "#199E70",
  name: "#C98500",
};

export const EVIDENCE_LABEL: Record<EvidenceGroup, string> = {
  id: "Strong ID (Aadhaar, ABHA, hospital ID)",
  contact: "Contact (phone, email)",
  name: "Name with context (DOB, village, relative)",
};

export function evidenceGroup(type: string): EvidenceGroup {
  if (/aadhaar|abha|hospital_id|pan|voter/i.test(type)) return "id";
  if (/phone|email/i.test(type)) return "contact";
  return "name";
}

export function prettyEvidence(type: string): string {
  return type.replaceAll("_", " ").replace("hospital id", "hospital ID").replace("abha", "ABHA").replace("aadhaar", "Aadhaar");
}
