import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// Three pages, mirroring the old static setup.html/student.html/lecturer.html
// -- each is its own entry point (not client-side routes) so the URLs a
// lecturer/student hits (and the ?question_id= links between them) stay the
// same as before.
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        setup: resolve(__dirname, "setup.html"),
        student: resolve(__dirname, "student.html"),
        lecturer: resolve(__dirname, "lecturer.html"),
      },
    },
  },
  server: {
    // Same-origin fetch("/api/...") calls in the app code assume the FastAPI
    // backend is at the same origin as the page (true once built and served
    // by FastAPI's StaticFiles). Proxy in dev so `npm run dev` works too.
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
