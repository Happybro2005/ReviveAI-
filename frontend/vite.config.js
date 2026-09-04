import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Backend origin the dev proxy forwards /api to. Override with API_ORIGIN if
// you run the backend somewhere else.
const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Fail loudly instead of silently drifting to 5174 when 5173 is taken.
    // A second instance on another port is how you end up debugging a page
    // that is not the one you are looking at.
    strictPort: true,
    proxy: {
      // The app calls relative "/api/...", so requests are same-origin and no
      // CORS is involved in development.
      "/api": {
        target: API_ORIGIN,
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 4173,
    strictPort: true,
    proxy: {
      "/api": { target: API_ORIGIN, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
});
