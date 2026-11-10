import { StrictMode } from "react";
import type { ComponentType } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./index.css";

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
