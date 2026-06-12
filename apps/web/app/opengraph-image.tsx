import { ImageResponse } from "next/og";

export const alt = "SaaS GenAI Starter — production-grade open-source GenAI SaaS boilerplate";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Code-generated social card — no binary asset to keep in the repo.
export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "80px",
          background: "linear-gradient(135deg, #09090b 0%, #1c1c22 100%)",
          color: "#fafafa",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", fontSize: 28, color: "#a1a1aa" }}>
          open source · MIT
        </div>
        <div style={{ display: "flex", fontSize: 76, fontWeight: 700, marginTop: 16 }}>
          SaaS GenAI Starter
        </div>
        <div
          style={{
            display: "flex",
            fontSize: 34,
            color: "#d4d4d8",
            marginTop: 24,
            lineHeight: 1.4,
          }}
        >
          Multi-tenant GenAI SaaS boilerplate — BYO-key LLM layer, RAG with
          citations, usage tracking, evals, $0 infra.
        </div>
        <div style={{ display: "flex", fontSize: 26, color: "#71717a", marginTop: 40 }}>
          Next.js 15 · FastAPI · Postgres + pgvector · Terraform
        </div>
      </div>
    ),
    size,
  );
}
