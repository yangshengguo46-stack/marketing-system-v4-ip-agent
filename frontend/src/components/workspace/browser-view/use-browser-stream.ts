"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { browserStreamURL } from "./api";

export interface BrowserTab {
  index: number;
  title: string;
  url: string;
  active: boolean;
}

export type BrowserInputEvent =
  | { type: "click"; nx: number; ny: number }
  | { type: "move"; nx: number; ny: number }
  | { type: "down"; nx: number; ny: number }
  | { type: "up"; nx: number; ny: number }
  | { type: "wheel"; dx: number; dy: number; nx?: number; ny?: number }
  | { type: "key"; key: string }
  | { type: "text"; text: string }
  | { type: "navigate"; url: string }
  | { type: "back" }
  | { type: "forward" }
  | { type: "activate_tab"; index: number };

export type BrowserStreamStatus = "idle" | "connecting" | "open" | "closed";
export type BrowserPresentationMode =
  | "pending"
  | "native_window"
  | "embedded_stream";

const RECONNECT_BASE_DELAY_MS = 800;
const RECONNECT_MAX_DELAY_MS = 10_000;
const RECONNECT_MAX_ATTEMPTS = 6;

function normalizeSeedUrl(url: string | null | undefined): string {
  return (url ?? "").split("#", 1)[0]?.replace(/\/+$/, "") ?? "";
}

/**
 * Manage a live browser screencast WebSocket.
 *
 * When ``enabled`` is true, opens the stream, exposes the latest JPEG frame as
 * a data URL, and returns a ``sendInput`` callback that forwards user input to
 * the live page. Closes and cleans up when disabled or unmounted.
 *
 * ``seedUrl`` is only read when a connection is first established (via a ref, so
 * it is NOT a reconnect trigger). A separate effect steers an already-open live
 * page toward a changed seed with an in-band ``navigate`` event, so ordinary
 * navigations no longer tear down and rebuild the socket.
 */
export function useBrowserStream(
  sessionId: string,
  enabled: boolean,
  seedUrl?: string,
  onNavRejected?: (
    url: string | undefined,
    message: string | undefined,
  ) => void,
  scope: "thread" | "account" = "thread",
) {
  const [status, setStatus] = useState<BrowserStreamStatus>("idle");
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [liveUrl, setLiveUrl] = useState<string | null>(null);
  const [tabs, setTabs] = useState<BrowserTab[]>([]);
  const [accountAuthenticated, setAccountAuthenticated] = useState(false);
  const [presentationMode, setPresentationMode] =
    useState<BrowserPresentationMode>("pending");
  const [connectionGeneration, setConnectionGeneration] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const presentationModeRef = useRef<BrowserPresentationMode>("pending");
  const pendingNavigateRef = useRef<Extract<
    BrowserInputEvent,
    { type: "navigate" }
  > | null>(null);
  // Read the seed at connect time only; it must not be a reconnect dependency.
  const seedRef = useRef(seedUrl);
  seedRef.current = seedUrl;
  // Latest live page URL reported by the server, used to decide whether an
  // open stream already shows the seed target (avoids redundant navigations).
  const liveUrlRef = useRef<string | null>(null);
  const onNavRejectedRef = useRef(onNavRejected);
  onNavRejectedRef.current = onNavRejected;

  const sendInput = useCallback((event: BrowserInputEvent) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(event));
      return true;
    }
    // URL bar submissions are user intent and must not be lost during the
    // short Live connection window right after opening the panel.
    if (event.type === "navigate") {
      pendingNavigateRef.current = event;
    }
    return false;
  }, []);

  useEffect(() => {
    pendingNavigateRef.current = null;
    setAccountAuthenticated(false);
    setPresentationMode("pending");
    presentationModeRef.current = "pending";
    reconnectAttemptRef.current = 0;
  }, [sessionId, scope]);

  useEffect(() => {
    if (enabled) {
      return;
    }
    setConnectionGeneration(0);
    reconnectAttemptRef.current = 0;
    setFrameUrl(null);
    setLiveUrl(null);
    setTabs([]);
    setPresentationMode("pending");
    presentationModeRef.current = "pending";
    liveUrlRef.current = null;
  }, [enabled, sessionId, scope]);

  useEffect(() => {
    if (!enabled) {
      setStatus("idle");
      liveUrlRef.current = null;
      return;
    }

    let closedByEffect = false;
    let reconnectTimer: number | null = null;
    let connectTimer: number | null = null;
    let socket: WebSocket | null = null;
    setStatus("connecting");
    // browserStreamURL treats empty/undefined seed identically (no seed param),
    // so the raw ref value is fine here. Record the seed optimistically so the
    // "steer to seed" effect below does not fire a duplicate navigate right
    // after open (the server already aligns the page to the connect-time seed).
    liveUrlRef.current = seedRef.current ?? null;

    const scheduleReconnect = () => {
      if (closedByEffect || !enabled) {
        return;
      }
      if (reconnectTimer !== null) {
        return;
      }
      // Once a real native Chromium is open, reconnecting this lifecycle
      // socket would open another native window/tab after a backend restart.
      if (
        scope === "account" &&
        presentationModeRef.current === "native_window"
      ) {
        return;
      }
      // Exponential backoff with a ceiling + attempt cap so a server that keeps
      // rejecting the upgrade cannot pin the client in a tight reconnect loop.
      const reconnectAttempt = reconnectAttemptRef.current;
      if (reconnectAttempt >= RECONNECT_MAX_ATTEMPTS) {
        return;
      }
      const delay = Math.min(
        RECONNECT_BASE_DELAY_MS * 2 ** reconnectAttempt,
        RECONNECT_MAX_DELAY_MS,
      );
      reconnectTimer = window.setTimeout(() => {
        reconnectAttemptRef.current += 1;
        setConnectionGeneration((generation) => generation + 1);
      }, delay);
    };

    // Defer creation by one task. React development Strict Mode immediately
    // mounts, cleans up, and mounts effects again; opening the socket
    // synchronously lets both mounts acquire the same retained browser session.
    // The first cleanup can then tear down the session underneath the second
    // connection. A deferred open is cancelled by that probe cleanup, leaving
    // exactly one real account-browser stream.
    connectTimer = window.setTimeout(() => {
      if (closedByEffect) {
        return;
      }
      const nextSocket = new WebSocket(
        browserStreamURL(sessionId, seedRef.current, scope),
      );
      socket = nextSocket;
      socketRef.current = nextSocket;

      nextSocket.onopen = () => {
        const pendingNavigate = pendingNavigateRef.current;
        if (pendingNavigate) {
          nextSocket.send(JSON.stringify(pendingNavigate));
          pendingNavigateRef.current = null;
        }
        // Reset the reconnect budget without changing this effect's dependency.
        // Changing it here tears down the socket that just opened and can launch
        // a second native account-login window.
        reconnectAttemptRef.current = 0;
        setStatus("open");
      };
      nextSocket.onmessage = async (message) => {
        try {
          const raw =
            typeof message.data === "string"
              ? message.data
              : message.data instanceof Blob
                ? await message.data.text()
                : message.data instanceof ArrayBuffer
                  ? new TextDecoder().decode(message.data)
                  : String(message.data);
          // The message may resolve after cleanup (async Blob/ArrayBuffer decode);
          // do not write state for a socket the effect already tore down.
          if (closedByEffect) {
            return;
          }
          const payload = JSON.parse(raw) as {
            type?: string;
            data?: string;
            url?: string;
            message?: string;
            tabs?: BrowserTab[];
            mode?: BrowserPresentationMode;
          };
          if (payload.type === "frame" && payload.data) {
            setFrameUrl(`data:image/jpeg;base64,${payload.data}`);
          } else if (
            payload.type === "presentation" &&
            (payload.mode === "native_window" ||
              payload.mode === "embedded_stream")
          ) {
            presentationModeRef.current = payload.mode;
            setPresentationMode(payload.mode);
          } else if (payload.type === "url" && payload.url) {
            liveUrlRef.current = payload.url;
            setLiveUrl(payload.url);
          } else if (payload.type === "tabs" && Array.isArray(payload.tabs)) {
            setTabs(payload.tabs);
          } else if (payload.type === "nav_rejected") {
            onNavRejectedRef.current?.(payload.url, payload.message);
          } else if (payload.type === "account_authenticated") {
            setAccountAuthenticated(true);
          }
        } catch (error) {
          console.warn("Ignoring malformed browser stream message", error);
        }
      };
      nextSocket.onclose = () => {
        if (!closedByEffect) {
          setStatus("closed");
          scheduleReconnect();
        }
      };
      nextSocket.onerror = () => {
        if (!closedByEffect) {
          setStatus("closed");
          scheduleReconnect();
        }
      };
    }, 0);

    return () => {
      closedByEffect = true;
      if (connectTimer !== null) {
        window.clearTimeout(connectTimer);
      }
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
      if (socketRef.current === socket) {
        socketRef.current = null;
      }
      socket?.close();
    };
  }, [connectionGeneration, enabled, scope, sessionId]);

  // Steer an already-open stream toward a changed seed in-band instead of
  // rebuilding the socket. Only navigates when the live page differs from the
  // seed target, so redirects/history moves the server already reflects do not
  // cause a redundant navigation loop.
  useEffect(() => {
    if (!enabled || status !== "open") {
      return;
    }
    const target = seedUrl?.trim();
    if (!target) {
      return;
    }
    if (normalizeSeedUrl(target) === normalizeSeedUrl(liveUrlRef.current)) {
      return;
    }
    sendInput({ type: "navigate", url: target });
  }, [enabled, seedUrl, sendInput, status]);

  return {
    status,
    frameUrl,
    liveUrl,
    tabs,
    accountAuthenticated,
    presentationMode,
    sendInput,
  };
}
