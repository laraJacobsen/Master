import { defineConfig } from "vite";
import type { Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { execSync } from "child_process";
import { readFileSync } from "fs";
import { resolve } from "path";

// Each page is its own entry point (not client-side routes). They're served
// at clean URLs (src/shared/routes.ts): this map is the one source of which
// path is which file, used by the dev server below -- backend/main.py keeps
// the same map for production. `home` is index.html, the site root;
// `present` is the projector view; 404.html is what unknown paths get.
const PAGES: Record<string, string> = {
  "/setup": "setup.html",
  "/live": "lecturer.html",
  "/history": "history.html",
  "/present": "present.html",
  "/join": "student.html",
  "/help": "help.html",
  "/privacy": "privacy.html",
};

// Dev-server and `vite preview` version of main.py's routing: clean path ->
// its HTML file, old *.html URL -> redirect to the clean one.
function cleanUrls(): Plugin {
  const legacy = Object.fromEntries(Object.entries(PAGES).map(([path, file]) => [`/${file}`, path]));
  legacy["/index.html"] = "/";
  const handle = (req: { url?: string }, res: { statusCode: number; setHeader: (k: string, v: string) => void; end: () => void }, next: () => void) => {
    const [pathname, query = ""] = (req.url ?? "/").split("?");
    const clean = pathname.length > 1 ? pathname.replace(/\/$/, "") : pathname;
    if (legacy[clean] && req.url) {
      res.statusCode = 301;
      res.setHeader("Location", legacy[clean] + (query ? `?${query}` : ""));
      res.end();
      return;
    }
    if (PAGES[clean]) req.url = `/${PAGES[clean]}${query ? `?${query}` : ""}`;
    // Anything else that looks like a page (no file extension, not Vite's or
    // the API's own paths) is a missing page: show 404.html, as main.py does.
    else if (clean !== "/" && !/\.[a-z0-9]+$/i.test(clean) && !/^\/(api|@|src|node_modules)\b/.test(clean)) {
      req.url = "/404.html";
    }
    next();
  };
  return {
    name: "clean-urls",
    configureServer(server) {
      server.middlewares.use(handle);
    },
    configurePreviewServer(server) {
      server.middlewares.use(handle);
    },
  };
}

function gitCommit(): string {
  try {
    return execSync("git rev-parse --short HEAD", { stdio: ["ignore", "pipe", "ignore"] }).toString().trim();
  } catch {
    return "";
  }
}

const pkg = JSON.parse(readFileSync(resolve(__dirname, "package.json"), "utf8")) as { version: string };

export default defineConfig({
  plugins: [cleanUrls(), react(), tailwindcss()],
  // Shown in the footer (src/shared/brand.ts).
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
    __APP_COMMIT__: JSON.stringify(gitCommit()),
  },
  build: {
    rollupOptions: {
      input: {
        home: resolve(__dirname, "index.html"),
        setup: resolve(__dirname, "setup.html"),
        student: resolve(__dirname, "student.html"),
        lecturer: resolve(__dirname, "lecturer.html"),
        history: resolve(__dirname, "history.html"),
        present: resolve(__dirname, "present.html"),
        help: resolve(__dirname, "help.html"),
        privacy: resolve(__dirname, "privacy.html"),
        notFound: resolve(__dirname, "404.html"),
      },
    },
  },
  server: {
    // Same-origin fetch("/api/...") calls in the app code assume the FastAPI
    // backend is at the same origin as the page (true once built and served
    // by FastAPI). Proxy in dev so `npm run dev` works too.
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
