import type { Metadata } from "next";
import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Usage" };

export default function UsagePage() {
  return (
    <PagePlaceholder
      title="Usage"
      description="LLM costs and token consumption, broken down by feature and model."
      ticket="SGS-026"
    />
  );
}
