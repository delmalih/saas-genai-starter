import type { Metadata } from "next";
import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Chat" };

export default function ChatPage() {
  return (
    <PagePlaceholder
      title="Chat"
      description="Streaming conversations with your documents, with citations."
      ticket="SGS-025"
    />
  );
}
