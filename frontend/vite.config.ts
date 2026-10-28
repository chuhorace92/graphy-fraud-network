import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // In dev the API runs on :8000 (make api, or docker compose up api).
    proxy: { "/api": "http://localhost:8000" },
  },
  build: {
    sourcemap: true,
    chunkSizeWarningLimit: 1500, // cytoscape is large; it is split into its own chunk
    rollupOptions: {
      output: { manualChunks: (id) => (id.includes("node_modules/cytoscape") ? "graph" : undefined) },
    },
  },
});
