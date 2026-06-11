// Active organization, shared between the React tree (OrgProvider) and the
// API client middleware (X-Org-Id header) without prop drilling.

const STORAGE_KEY = "active-org-id";

let activeOrgId: string | null = null;

export function getActiveOrgId(): string | null {
  if (activeOrgId === null && typeof window !== "undefined") {
    activeOrgId = window.localStorage.getItem(STORAGE_KEY);
  }
  return activeOrgId;
}

export function setActiveOrgId(orgId: string): void {
  activeOrgId = orgId;
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, orgId);
  }
}
