// SPDX-FileCopyrightText: 2026 Curtis Galloway
// SPDX-License-Identifier: Apache-2.0

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { loadData } from "./load";
import "./styles.css";

// order-history's page.py fills this element with the order data; the shell
// is built with it empty.
const loaded = loadData(document.getElementById("order-data")?.textContent);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {loaded.ok ? (
      <App data={loaded.data} />
    ) : (
      <div className="slip">
        <div className="empty" role="alert" id="page-message">
          <div className="big">No manifest</div>
          <div>{loaded.message}</div>
        </div>
      </div>
    )}
  </StrictMode>,
);
