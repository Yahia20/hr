import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource-variable/dm-sans";
import "@fontsource-variable/noto-sans-arabic";
import "./theme.css";
import HRSystem from "./App.jsx";
import ErrorBoundary from "./ErrorBoundary.jsx";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorBoundary>
      <HRSystem />
    </ErrorBoundary>
  </React.StrictMode>
);
