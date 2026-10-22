import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The FastAPI gateway has no CORS middleware, so the dev server proxies API
// calls to the backend (same role nginx plays in the documented deployment).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
