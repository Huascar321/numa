import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "NUMA_");
  const apiTarget = env.NUMA_API_TARGET || "http://127.0.0.1:39748";
  return {
    plugins: [react()],
    server: {
      host: "localhost",
      port: 5173,
      strictPort: true,
      proxy: {
        "/plans": {
          target: apiTarget,
          bypass(request) {
            // Browser navigation loads the SPA; fetch requests reach the API.
            if (request.method === "GET" && request.headers.accept?.includes("text/html")) {
              return "/index.html";
            }
          },
        },
        "/currencies": apiTarget,
        "/health": apiTarget,
        "/gmail/oauth": apiTarget,
      },
    },
  };
});
