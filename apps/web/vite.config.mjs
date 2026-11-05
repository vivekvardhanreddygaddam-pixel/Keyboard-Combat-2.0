import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  server: {
    port: 5173,
    host: "127.0.0.1",
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
      "/healthz": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/readyz": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, "index.html"),
        events: resolve(__dirname, "events/index.html"),
        organizations: resolve(__dirname, "organizations/index.html"),
        leaderboards: resolve(__dirname, "leaderboards/index.html"),
        results: resolve(__dirname, "results/index.html"),
        help: resolve(__dirname, "help/index.html"),
        about: resolve(__dirname, "about/index.html"),
        login: resolve(__dirname, "login/index.html"),
        register: resolve(__dirname, "register/index.html"),
        account: resolve(__dirname, "account/index.html"),
        practice: resolve(__dirname, "practice/index.html"),
        arena: resolve(__dirname, "arena/index.html"),
        command: resolve(__dirname, "command/index.html"),
      },
    },
  },
});
