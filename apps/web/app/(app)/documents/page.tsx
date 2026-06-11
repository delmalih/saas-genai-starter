import type { Metadata } from "next";
import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Documents" };

export default function DocumentsPage() {
  return (
    <PagePlaceholder
      title="Documents"
      description="Upload documents and track their ingestion status."
      ticket="SGS-036"
    />
  );
}
