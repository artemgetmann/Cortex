import React from "react";
import { createRoot } from "react-dom/client";
import AGIIdeas from "../../agi-ideas.jsx";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AGIIdeas />
  </React.StrictMode>,
);
