import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import "./index.css";
import { cleanupLegacyAccessToken } from "./lib/api";
import { queryClient } from "./lib/queryClient";
import { TenantProvider } from "./lib/tenant";

if (localStorage.getItem("makerspace.theme") === "dark") {
  document.documentElement.classList.add("dark");
}
// Blueprint grid is on by default; only mark the DOM when it was turned off (FOUC-safe).
document.documentElement.setAttribute(
  "data-grid",
  localStorage.getItem("makerspace.grid") === "off" ? "off" : "on",
);
cleanupLegacyAccessToken();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <TenantProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </TenantProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
