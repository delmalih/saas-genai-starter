import type { Metadata } from "next";
import { DocumentsView } from "@/components/documents/documents-view";

export const metadata: Metadata = { title: "Documents" };

export default function DocumentsPage() {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 py-2">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight">Documents</h1>
        <p className="text-sm text-muted-foreground">
          Upload documents and chat with their content.
        </p>
      </div>
      <DocumentsView />
    </div>
  );
}
