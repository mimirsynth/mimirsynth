// ui-ok-file: marca y tema (colores propios de la identidad)
import React from "react";
import ReactDOM from "react-dom/client";
import { createTheme, MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import "@mantine/core/styles.css";
import "./theme.css";
import App from "./App";

const mimir = ["#e6f3f3", "#cfe4e1", "#a6d2d3", "#7cc0c4", "#5fb8bf", "#3f9aa3", "#2d8189", "#1e6b73", "#18565d", "#12424a"] as const;
const hidromiel = ["#fbf3e1", "#f5e4bd", "#efd592", "#e8c56a", "#d4a03a", "#d4a03a", "#d4a03a", "#d4a03a", "#b9862a", "#946a20"] as const;
const theme = createTheme({
  primaryColor: "mimir", colors: { mimir: [...mimir], hidromiel: [...hidromiel] }, primaryShade: { light: 7, dark: 4 }, defaultRadius: "sm",
  fontFamily: 'var(--ms-sans)', headings: { fontFamily: 'var(--ms-display)', fontWeight: "600" }, fontFamilyMonospace: 'var(--ms-mono)',
  radius: { xs: "6px", sm: "6px", md: "6px", lg: "10px", xl: "10px" },
});

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <QueryClientProvider client={qc}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </MantineProvider>
  </React.StrictMode>,
);
