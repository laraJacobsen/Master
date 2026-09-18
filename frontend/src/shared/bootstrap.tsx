import { StrictMode } from "react";
import type { ComponentType } from "react";
import { createRoot } from "react-dom/client";
import "./base.css";

// Every page's main.tsx did this exact StrictMode/createRoot dance --
// pulled out once here, imported first (before that page's own style.css)
// so base.css's rules load before any page-specific override.
export function mountApp(App: ComponentType) {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>
  );
}
