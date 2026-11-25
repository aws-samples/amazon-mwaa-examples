/* Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: MIT-0 */
/* Global "AI Agent" launcher for Airflow 3.2+.
 *
 * Registered as a react_apps entry with destination "base", so Airflow renders it on every page and
 * passes the current route's {dagId, runId, taskId, mapIndex}. It uses the host's React
 * (globalThis.React, exposed by Airflow 3.2+), so there is no build step.
 *
 * The chat itself is the same page as the nav view (/mwaa-agent/), loaded once in a same-origin
 * iframe. Route changes are sent to it with postMessage, so the conversation survives navigation.
 */
const React = globalThis.React;
const h = React.createElement;
const { useEffect, useRef, useState, useCallback } = React;

const AGENT_BASE = new URL("../", import.meta.url); // .../mwaa-agent/
const OPEN_KEY = "mwaa-agent:launcher-open";
const MESSAGE_TYPE = "mwaa-agent:page";

function readOpen() {
  try {
    return window.sessionStorage.getItem(OPEN_KEY) === "1";
  } catch (e) {
    return false;
  }
}

function writeOpen(value) {
  try {
    window.sessionStorage.setItem(OPEN_KEY, value ? "1" : "0");
  } catch (e) {
    /* ignore */
  }
}

const styles = {
  button: {
    position: "fixed",
    right: "20px",
    bottom: "20px",
    zIndex: 1400,
    border: "none",
    borderRadius: "999px",
    padding: "10px 18px",
    background: "#017cee",
    color: "#ffffff",
    font: "600 14px/1.2 -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    boxShadow: "0 4px 14px rgba(0, 0, 0, 0.25)",
    cursor: "pointer",
  },
  panel: {
    position: "fixed",
    right: "20px",
    bottom: "72px",
    zIndex: 1400,
    width: "min(480px, calc(100vw - 40px))",
    height: "min(760px, calc(100vh - 100px))",
    borderRadius: "12px",
    overflow: "hidden",
    boxShadow: "0 12px 40px rgba(0, 0, 0, 0.35)",
    background: "#ffffff",
  },
  frame: { border: "none", width: "100%", height: "100%", display: "block" },
};

function toPage(props) {
  const mapIndex = props.mapIndex === undefined || props.mapIndex === null ? null : parseInt(props.mapIndex, 10);
  return {
    dag_id: props.dagId || null,
    run_id: props.runId || null,
    task_id: props.taskId || null,
    map_index: Number.isNaN(mapIndex) ? null : mapIndex,
  };
}

function MwaaAgentLauncher(props) {
  const [open, setOpen] = useState(readOpen);
  const [mounted, setMounted] = useState(readOpen);
  const frameRef = useRef(null);
  const page = toPage(props);
  const pageKey = JSON.stringify(page);

  useEffect(() => {
    if (open) setMounted(true);
  }, [open]);

  const postPage = useCallback(() => {
    const frame = frameRef.current;
    if (frame && frame.contentWindow) {
      frame.contentWindow.postMessage({ type: MESSAGE_TYPE, page: JSON.parse(pageKey) }, window.location.origin);
    }
  }, [pageKey]);

  useEffect(postPage, [postPage, open]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => writeOpen(open), [open]);

  // The full-page nav view already shows the chat.
  if (window.location.pathname.indexOf("/plugin/mwaa-agent") !== -1) return null;

  const src = new URL("?embed=1", AGENT_BASE).toString();
  return h(
    React.Fragment,
    null,
    h(
      "div",
      {
        id: "mwaa-agent-panel",
        role: "dialog",
        "aria-label": "AI Agent",
        "aria-modal": "false",
        hidden: !open,
        style: open ? styles.panel : { display: "none" },
      },
      // Loaded on first open, then kept mounted so the conversation and in-flight answers survive.
      mounted ? h("iframe", { ref: frameRef, src: src, title: "AI Agent", style: styles.frame, onLoad: postPage }) : null
    ),
    h(
      "button",
      {
        type: "button",
        style: styles.button,
        "aria-expanded": open ? "true" : "false",
        "aria-controls": "mwaa-agent-panel",
        onClick: () => setOpen(!open),
      },
      open ? "Close AI Agent" : "AI Agent"
    )
  );
}

globalThis["MWAA AI Agent"] = MwaaAgentLauncher;
export default MwaaAgentLauncher;
