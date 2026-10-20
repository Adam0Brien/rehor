import { createVertexAnthropic } from "@ai-sdk/google-vertex/anthropic";

const PLACEHOLDER_TOKEN = "rehor-proxy-placeholder";
const DUMMY_PROJECT = "dummy-project";
const DUMMY_REGION = "dummy-region";

interface VertexProxyProviderOptions {
  baseURL?: string;
}

/**
 * OpenCode adapter for Claude on Vertex through the existing Rehor proxy.
 *
 * The provider SDK normally obtains Google ADC itself. Rehor keeps its service
 * account on the proxy, so this adapter sends a placeholder bearer token. The
 * proxy replaces it with its own SA token and rewrites the dummy resource path.
 */
export function createVertexProxyProvider(options: VertexProxyProviderOptions) {
  const proxyRoot = new URL(options.baseURL ?? "http://devbot-proxy:8443");
  if (
    proxyRoot.protocol !== "http:" ||
    proxyRoot.port !== "8443" ||
    !proxyRoot.hostname ||
    proxyRoot.username ||
    proxyRoot.password ||
    (proxyRoot.pathname !== "" && proxyRoot.pathname !== "/") ||
    proxyRoot.search ||
    proxyRoot.hash
  ) {
    throw new Error("Vertex provider must use Rehor proxy at http://<proxy-host>:8443");
  }

  const baseURL = new URL(
    `/v1/projects/${DUMMY_PROJECT}/locations/${DUMMY_REGION}/publishers/anthropic/models`,
    proxyRoot.origin,
  ).toString();

  return createVertexAnthropic({
    baseURL,
    project: DUMMY_PROJECT,
    location: DUMMY_REGION,
    generateAuthToken: async () => PLACEHOLDER_TOKEN,
  });
}
