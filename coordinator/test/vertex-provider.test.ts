import { describe, expect, it } from "vitest";

import { createVertexProxyProvider } from "../src/runtimes/opencode-v1/vertex-provider";

describe("Vertex proxy provider adapter", () => {
  it("constructs Claude models without loading Google ADC in OpenCode", () => {
    const previousCredentials = process.env.GOOGLE_APPLICATION_CREDENTIALS;
    delete process.env.GOOGLE_APPLICATION_CREDENTIALS;
    try {
      const provider = createVertexProxyProvider({ baseURL: "http://devbot-proxy:8443" });

      expect(provider.languageModel("claude-opus-4-6")).toBeDefined();
      expect(provider.languageModel("claude-sonnet-4-6")).toBeDefined();
      expect(provider.languageModel("claude-haiku-4-5@20251001")).toBeDefined();
    } finally {
      if (previousCredentials === undefined) delete process.env.GOOGLE_APPLICATION_CREDENTIALS;
      else process.env.GOOGLE_APPLICATION_CREDENTIALS = previousCredentials;
    }
  });

  it("rejects provider URLs that bypass the Vertex auth proxy", () => {
    expect(() =>
      createVertexProxyProvider({ baseURL: "https://aiplatform.googleapis.com" }),
    ).toThrow("Vertex provider must use Rehor proxy");
  });
});
