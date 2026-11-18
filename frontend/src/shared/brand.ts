// The product's name and tagline, in one place: the nav bar, page titles,
// footer, help and privacy pages all read from here, so renaming the product
// is a one-line change (plus the <title>/meta tags in the six *.html shells
// and public/site.webmanifest, which can't import this).
export const BRAND = {
  name: "Classloop",
  tagline: "Live coding exercises for lectures",
} as const;

// Injected at build time by vite.config.ts (package.json version + git commit).
declare const __APP_VERSION__: string;
declare const __APP_COMMIT__: string;
export const APP_VERSION: string = __APP_VERSION__;
export const APP_COMMIT: string = __APP_COMMIT__;
