import { StrictMode } from "react";
import type { ComponentType } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/poppins/400.css";
import "@fontsource/poppins/500.css";
import "@fontsource/poppins/600.css";
import "@fontsource/poppins/700.css";
import "@fontsource-variable/jetbrains-mono";
import "./index.css";
import { LecturerGate } from "./LecturerGate";
import { Toaster } from "./toast";
import { ConnectionBanner } from "./ConnectionBanner";

// Every page's main.tsx did this exact StrictMode/createRoot dance --
// pulled out once here, together with the font, the one Tailwind
// stylesheet every page shares, and the page-wide overlays (toasts and the
// "connection lost" banner).
export function mountApp(App: ComponentType) {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
      <Toaster />
      <ConnectionBanner />
    </StrictMode>
  );
}

// The lecturer's pages: same, behind the lecturer login (see LecturerGate).
export function mountLecturerApp(App: ComponentType) {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <LecturerGate>
        <App />
      </LecturerGate>
      <Toaster />
      <ConnectionBanner />
    </StrictMode>
  );
}
