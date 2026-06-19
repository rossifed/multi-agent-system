import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// Frontend dev server runs on :3000; build output is static and served by nginx
// in production (see Dockerfile).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 3000, host: true },
});
