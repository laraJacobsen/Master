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

// Every page's main.tsx did this exact StrictMode/createRoot dance --
// pulled out once here, together with the font and the one Tailwind
// stylesheet every page shares.
export function mountApp(App: ComponentType) {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
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
    </StrictMode>
  );
}
