import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const features = [
  {
    title: "Multi-tenancy built in",
    description:
      "Organizations, roles and invitations — every query tenant-scoped at the repository layer.",
  },
  {
    title: "LLM costs under control",
    description:
      "Tokens, cost and latency tracked per tenant and per feature. Rate limiting included.",
  },
  {
    title: "Production-grade plumbing",
    description:
      "Retries, circuit breakers, streaming, OpenTelemetry, Terraform on GCP — the parts demos skip.",
  },
  {
    title: "Evals from day one",
    description:
      "A RAG evaluation harness with LLM-as-judge scoring, wired into the workflow.",
  },
] as const;

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "SaaS GenAI Starter",
  applicationCategory: "DeveloperApplication",
  operatingSystem: "Web",
  description:
    "Production-grade open-source SaaS starter for GenAI products: multi-tenancy, BYO-key LLM layer, RAG with citations, usage tracking, evals, infrastructure as code.",
  license: "https://opensource.org/license/mit",
  url: "https://github.com/delmalih/saas-genai-starter",
  offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
};

export default function MarketingPage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4">
      <script
        type="application/ld+json"
        // Static literal above — nothing user-controlled is interpolated.
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <section className="flex flex-col items-center gap-6 py-24 text-center">
        <h1 className="max-w-3xl font-heading text-4xl font-bold tracking-tight sm:text-5xl">
          The production-grade starter for GenAI products
        </h1>
        <p className="max-w-2xl text-lg text-muted-foreground">
          Multi-tenant SaaS foundations with the LLM layer done right: cost tracking,
          resilience, observability, infra as code — open source, MIT licensed.
        </p>
        <div className="flex gap-3">
          <Button asChild size="lg">
            <Link href="/chat">Open the demo app</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <a href="https://github.com/delmalih/saas-genai-starter">
              Star on GitHub
            </a>
          </Button>
        </div>
      </section>
      <section className="grid gap-4 pb-24 sm:grid-cols-2">
        {features.map((feature) => (
          <Card key={feature.title}>
            <CardHeader>
              <CardTitle>{feature.title}</CardTitle>
              <CardDescription>{feature.description}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </section>
    </div>
  );
}
