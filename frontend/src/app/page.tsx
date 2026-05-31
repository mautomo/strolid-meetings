"use client";

import { useEffect, useState, useRef } from "react";
import { 
  signInWithEmailAndPassword, 
  signOut, 
  onAuthStateChanged,
  signInWithPhoneNumber,
  RecaptchaVerifier,
  ConfirmationResult,
  GoogleAuthProvider,
  signInWithPopup
} from "firebase/auth";
import { collection, query, orderBy, onSnapshot, limit } from "firebase/firestore";
import { auth, db } from "./firebase";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./globals.css";

const API_BASE = typeof window !== "undefined" && window.location.hostname === "localhost"
  ? "http://localhost:8000"
  : "";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  artifact?: any;
  timestamp?: any;
}

function renderMarkdown(text: string) {
  if (!text) return null;
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Preserve the existing table styling (globals.css .table-container / .markdown-table)
          table: (props) => (
            <div className="table-container">
              <table className="markdown-table" {...props} />
            </div>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

const GeminiSparkle = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M12 2C12 7.52285 7.52285 12 2 12C7.52285 12 12 16.4771 12 22C12 16.4771 16.4771 12 22 12C16.4771 12 12 7.52285 12 2Z" fill="url(#gemini-grad)"/>
    <defs>
      <linearGradient id="gemini-grad" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
        <stop stopColor="#3b82f6"/>
        <stop offset="1" stopColor="#8b5cf6"/>
      </linearGradient>
    </defs>
  </svg>
);

const UserIcon = () => (
  <div style={{
    width: "32px",
    height: "32px",
    borderRadius: "50%",
    background: "rgba(255, 255, 255, 0.08)",
    border: "1px solid rgba(255, 255, 255, 0.15)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "0.85rem",
    fontWeight: "bold",
    color: "white",
    flexShrink: 0
  }}>
    U
  </div>
);

export default function Home() {
  // Auth State
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [authMode, setAuthMode] = useState<"email" | "phone">("email");
  const [confirmationResult, setConfirmationResult] = useState<ConfirmationResult | null>(null);
  const [authError, setAuthError] = useState("");

  // Chat State
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState("session-strolid-q4-2025");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [chatError, setChatError] = useState("");
  const [lastUserMessage, setLastUserMessage] = useState("");
  
  // Date and meeting filtering states
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [selectedMeetingIds, setSelectedMeetingIds] = useState<string[]>([]);

  // Dynamic Meetings and Stats state
  const [meetings, setMeetings] = useState<any[]>([]);
  const [stats, setStats] = useState({ meetings_count: 53, decisions_count: 225 });

  // Artifact View State
  const [activeArtifact, setActiveArtifact] = useState<any>(null);
  const [slideIndex, setSlideIndex] = useState(0);

  const uniqueMeetings = Array.from(new Map(meetings.map(m => [m.meeting_id, m])).values());

  // Recaptcha for Phone Auth
  const recaptchaVerifierRef = useRef<any>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  // Check Auth State
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (u) => {
      setUser(u);
      setLoading(false);
    });
    return () => unsubscribe();
  }, []);

  // Fetch Meetings and Stats dynamically when authenticated
  useEffect(() => {
    if (!user) return;
    const fetchMeetingsAndStats = async () => {
      try {
        const token = await user.getIdToken();
        const headers: Record<string, string> = {
          "x-firebase-auth": token
        };
        
        const [meetingsRes, statsRes] = await Promise.all([
          fetch(`${API_BASE}/api/meetings`, { headers }),
          fetch(`${API_BASE}/api/stats`, { headers })
        ]);

        if (meetingsRes.ok) {
          const meetingsData = await meetingsRes.json();
          const ms = meetingsData.meetings || [];
          setMeetings(ms);
          // By default, select all meetings
          setSelectedMeetingIds(ms.map((m: any) => m.meeting_id));
        }
        
        if (statsRes.ok) {
          const statsData = await statsRes.json();
          setStats(statsData);
        }
      } catch (err) {
        console.error("Failed to fetch meetings/stats:", err);
      }
    };
    fetchMeetingsAndStats();
  }, [user]);

  // Listen to Firestore Chat Messages when logged in
  useEffect(() => {
    if (!user || !db) return;

    // Switching sessions: clear stale canvas/errors before the new listener repopulates.
    setActiveArtifact(null);
    setChatError("");

    const msgsRef = collection(db, "sessions", sessionId, "messages");
    const q = query(msgsRef, orderBy("timestamp", "asc"));

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const msgs: Message[] = [];
      snapshot.forEach((doc) => {
        const data = doc.data();
        msgs.push({
          id: doc.id,
          role: data.role,
          content: data.content,
          artifact: data.artifact,
          timestamp: data.timestamp
        });
      });
      setMessages(msgs);
      
      // Auto open the latest generated artifact if present
      const lastMsg = msgs[msgs.length - 1];
      if (lastMsg && lastMsg.artifact) {
        setActiveArtifact(lastMsg.artifact);
        if (lastMsg.artifact.artifact_type === "presentation") {
          setSlideIndex(0);
        }
      }
    });

    return () => unsubscribe();
  }, [user, sessionId]);

  // Scroll to bottom
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages, streamText]);

  // Handle Email Login
  const handleEmailLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    try {
      await signInWithEmailAndPassword(auth, email, password);
    } catch (err: any) {
      setAuthError(err.message || "Email authentication failed.");
    }
  };

  // Handle Google OAuth SSO
  const handleGoogleLogin = async () => {
    setAuthError("");
    const provider = new GoogleAuthProvider();
    try {
      await signInWithPopup(auth, provider);
    } catch (err: any) {
      setAuthError(err.message || "Google authentication failed.");
    }
  };

  // Handle Logout
  const handleSignOut = async () => {
    await signOut(auth);
  };

  // Initialize Recaptcha for Phone Auth
  const setupRecaptcha = () => {
    if (recaptchaVerifierRef.current) return;
    try {
      recaptchaVerifierRef.current = new RecaptchaVerifier(auth, "recaptcha-container", {
        size: "invisible",
        callback: () => {
          console.log("Recaptcha resolved");
        }
      });
    } catch (err) {
      console.error("Recaptcha setup error:", err);
    }
  };

  // Handle Send Verification SMS
  const handleSendCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    setupRecaptcha();
    const verifier = recaptchaVerifierRef.current;
    
    try {
      const confirmation = await signInWithPhoneNumber(auth, phone, verifier);
      setConfirmationResult(confirmation);
    } catch (err: any) {
      setAuthError(err.message || "Failed to send verification SMS.");
    }
  };

  // Handle Verify SMS Code
  const handleVerifyCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!confirmationResult) return;
    setAuthError("");
    try {
      await confirmationResult.confirm(verificationCode);
    } catch (err: any) {
      setAuthError(err.message || "Invalid SMS verification code.");
    }
  };

  // Send a message to the FastAPI ADK chatbot and consume the SSE stream.
  const sendMessage = async (userMsgText: string) => {
    if (!userMsgText.trim() || isStreaming) return;

    // Date-range sanity check before hitting the backend.
    if (startDate && endDate && startDate > endDate) {
      setChatError("Start date must be on or before the end date.");
      return;
    }

    setChatError("");
    setLastUserMessage(userMsgText);
    setIsStreaming(true);
    setStreamText("");

    const controller = new AbortController();
    // Idle timeout: abort only if the stream stalls (no data) for 45s, rather than
    // capping total duration, so long but healthy responses are not cut off.
    let idleTimer: ReturnType<typeof setTimeout> = setTimeout(() => controller.abort(), 45000);
    const resetIdle = () => {
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => controller.abort(), 45000);
    };

    try {
      const token = await user.getIdToken();
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-firebase-auth": token,
        },
        body: JSON.stringify({
          session_id: sessionId,
          user_id: user?.uid || "anonymous",
          message: userMsgText,
          start_date: startDate || null,
          end_date: endDate || null,
          selected_meeting_ids: selectedMeetingIds.length > 0 ? selectedMeetingIds : null,
        }),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`API request failed (${response.status}).`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let streamErr: string | null = null;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        resetIdle();
        buffer += decoder.decode(value, { stream: true });

        // SSE frames are separated by a blank line.
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const dataLine = frame.split("\n").find((l) => l.startsWith("data:"));
          if (!dataLine) continue;
          let evt: any;
          try {
            evt = JSON.parse(dataLine.slice(5).trim());
          } catch {
            continue;
          }
          if (evt.type === "token") {
            setStreamText((prev) => prev + (evt.text || ""));
          } else if (evt.type === "artifact" && evt.payload) {
            setActiveArtifact(evt.payload);
            if (evt.payload.artifact_type === "presentation") setSlideIndex(0);
          } else if (evt.type === "error") {
            streamErr = evt.message || "The assistant hit an error.";
          }
        }
      }

      if (streamErr) setChatError(streamErr);
    } catch (err: any) {
      if (err?.name === "AbortError") {
        setChatError("The request timed out. Please try again.");
      } else {
        console.error("Chat error:", err);
        setChatError("Couldn't reach the assistant. Check your connection and try again.");
      }
    } finally {
      clearTimeout(idleTimer);
      setIsStreaming(false);
      setStreamText("");
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = input;
    setInput("");
    await sendMessage(text);
  };

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <p style={{ color: "var(--accent)", fontSize: "1.2rem", fontWeight: 600 }}>Loading Strolid Platform...</p>
      </div>
    );
  }

  // Auth Screen
  if (!user) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", padding: "1rem" }}>
        <div className="glass-panel" style={{ width: "100%", maxWidth: "450px", padding: "2.5rem", borderRadius: "24px" }}>
          <h1 style={{ fontSize: "1.8rem", fontWeight: 800, textAlign: "center", marginBottom: "0.25rem", color: "white" }}>
            Strolid Meetings
          </h1>
          <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", textAlign: "center", marginBottom: "2rem" }}>
            AI-Powered Scorecard & Conversational RAG
          </p>

          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
            <button 
              className={authMode === "email" ? "btn-primary" : "btn-secondary"} 
              style={{ flex: 1, padding: "0.5rem" }}
              onClick={() => { setAuthMode("email"); setAuthError(""); }}
            >
              Email Sign-In
            </button>
            <button 
              className={authMode === "phone" ? "btn-primary" : "btn-secondary"} 
              style={{ flex: 1, padding: "0.5rem" }}
              onClick={() => { setAuthMode("phone"); setAuthError(""); }}
            >
              Phone Sign-In
            </button>
          </div>

          {authError && (
            <div style={{ padding: "0.75rem", background: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--red)", borderRadius: "8px", color: "var(--red)", fontSize: "0.85rem", marginBottom: "1rem" }}>
              {authError}
            </div>
          )}

          {authMode === "email" ? (
            <form onSubmit={handleEmailLogin} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Email Address</label>
                <input type="email" placeholder="you@domain.com" required value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Password</label>
                <input type="password" placeholder="••••••••" required value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
              <button type="submit" className="btn-primary" style={{ marginTop: "0.5rem" }}>Sign In</button>
            </form>
          ) : (
            <div>
              {!confirmationResult ? (
                <form onSubmit={handleSendCode} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                    <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Phone Number (International format)</label>
                    <input type="tel" placeholder="+15551234567" required value={phone} onChange={(e) => setPhone(e.target.value)} />
                  </div>
                  <div id="recaptcha-container"></div>
                  <button type="submit" className="btn-primary" style={{ marginTop: "0.5rem" }}>Send Verification SMS</button>
                </form>
              ) : (
                <form onSubmit={handleVerifyCode} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                    <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>6-Digit SMS Code</label>
                    <input type="text" placeholder="123456" required value={verificationCode} onChange={(e) => setVerificationCode(e.target.value)} />
                  </div>
                  <button type="submit" className="btn-primary" style={{ marginTop: "0.5rem" }}>Verify & Login</button>
                </form>
              )}
            </div>
          )}

          <div style={{ margin: "1.5rem 0", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <div style={{ flex: 1, height: "1px", background: "var(--border-glass)" }} />
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>or</span>
            <div style={{ flex: 1, height: "1px", background: "var(--border-glass)" }} />
          </div>

          <button 
            type="button" 
            className="btn-secondary" 
            style={{ width: "100%", padding: "0.75rem", display: "flex", justifyContent: "center", alignItems: "center", gap: "0.75rem", borderRadius: "8px", fontWeight: 600 }}
            onClick={handleGoogleLogin}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" fill="#EA4335"/>
            </svg>
            Continue with Google
          </button>
        </div>
      </div>
    );
  }

  // Dashboard / Chat Interface
  return (
    <div style={{ display: "grid", gridTemplateColumns: "280px 1fr 480px", height: "100vh", overflow: "hidden" }}>
      
      {/* 1. Left Sidebar: Navigation & Session Info */}
      <aside className="glass-panel" style={{ padding: "1.5rem", display: "flex", flexDirection: "column", borderRight: "1px solid var(--border-glass)", height: "100%", overflow: "hidden" }}>
        <div style={{ marginBottom: "2rem" }}>
          <h2 style={{ fontSize: "1.2rem", fontWeight: 800, color: "white", marginBottom: "0.25rem" }}>Strolid Hub</h2>
          <span style={{ fontSize: "0.75rem", color: "var(--accent)", fontWeight: 700 }}>MEETING INTELLIGENCE v2.0</span>
        </div>

        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "1rem", minHeight: 0 }}>
          <div>
            <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>Select Chat Scope</label>
            <select 
              value={sessionId} 
              onChange={(e) => {
                const val = e.target.value;
                setSessionId(val);
                if (val.startsWith("session-meeting-")) {
                  const mId = val.replace("session-meeting-", "");
                  setSelectedMeetingIds([mId]);
                } else {
                  setSelectedMeetingIds(uniqueMeetings.map(m => m.meeting_id));
                }
              }} 
              style={{ width: "100%", marginTop: "0.4rem" }}
            >
              <optgroup label="Global Sessions">
                <option value="session-strolid-q4-2025">Vinnie & Michael Sync (Q4 2025)</option>
                <option value="session-leadership-overall">Leadership Meetings (2025-2026)</option>
              </optgroup>
              <optgroup label="Individual Meetings">
                {uniqueMeetings.map((m) => (
                  <option key={m.meeting_id} value={`session-meeting-${m.meeting_id}`}>
                    {m.date} - {m.title || m.meeting_id}
                  </option>
                ))}
              </optgroup>
            </select>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>Date Range</label>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <input 
                type="date" 
                value={startDate} 
                onChange={(e) => setStartDate(e.target.value)} 
                style={{ width: "50%", padding: "0.5rem", fontSize: "0.8rem", height: "36px" }}
              />
              <input 
                type="date" 
                value={endDate} 
                onChange={(e) => setEndDate(e.target.value)} 
                style={{ width: "50%", padding: "0.5rem", fontSize: "0.8rem", height: "36px" }}
              />
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", flex: 1, minHeight: 0 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>Selected Meetings</label>
              <div style={{ display: "flex", gap: "0.4rem", fontSize: "0.7rem" }}>
                <button 
                  onClick={() => setSelectedMeetingIds(uniqueMeetings.map(m => m.meeting_id))}
                  style={{ background: "transparent", color: "var(--accent)", fontWeight: 600, padding: 0 }}
                  type="button"
                >
                  All
                </button>
                <span style={{ color: "var(--border-glass)" }}>|</span>
                <button 
                  onClick={() => setSelectedMeetingIds([])}
                  style={{ background: "transparent", color: "var(--accent)", fontWeight: 600, padding: 0 }}
                  type="button"
                >
                  None
                </button>
              </div>
            </div>
            
            <div className="custom-scrollbar" style={{ 
              flex: 1, 
              overflowY: "auto", 
              background: "rgba(0, 0, 0, 0.15)", 
              border: "1px solid var(--border-glass)", 
              borderRadius: "10px", 
              padding: "0.5rem"
            }}>
              {uniqueMeetings.map((m) => {
                const isChecked = selectedMeetingIds.includes(m.meeting_id);
                return (
                  <label 
                    key={m.meeting_id} 
                    style={{ 
                      display: "flex", 
                      alignItems: "center", 
                      gap: "0.5rem", 
                      padding: "0.35rem 0.5rem", 
                      borderRadius: "6px",
                      cursor: "pointer",
                      fontSize: "0.8rem",
                      background: isChecked ? "rgba(59, 130, 246, 0.05)" : "transparent",
                      color: isChecked ? "white" : "var(--text-muted)",
                      transition: "all 0.2s"
                    }}
                  >
                    <input 
                      type="checkbox" 
                      checked={isChecked}
                      onChange={() => {
                        if (isChecked) {
                          setSelectedMeetingIds(prev => prev.filter(id => id !== m.meeting_id));
                        } else {
                          setSelectedMeetingIds(prev => [...prev, m.meeting_id]);
                        }
                      }}
                      style={{ cursor: "pointer", width: "14px", height: "14px", accentColor: "var(--accent)" }}
                    />
                    <span style={{ textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap" }} title={m.title || m.meeting_id}>
                      {m.date} - {m.title || m.meeting_id}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          <div style={{ marginTop: "2rem" }}>
            <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>Quick Stats</label>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
              <div className="glass-card" style={{ padding: "0.75rem 1rem", background: "rgba(255,255,255,0.02)" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Meeting Count</div>
                <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "white" }}>{stats.meetings_count}</div>
              </div>
              <div className="glass-card" style={{ padding: "0.75rem 1rem", background: "rgba(255,255,255,0.02)" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Decisions Tracked</div>
                <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--green)" }}>{stats.decisions_count}</div>
              </div>
            </div>
          </div>
        </div>

        <div style={{ borderTop: "1px solid var(--border-glass)", paddingTop: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap" }}>
            {user.phoneNumber || user.email}
          </div>
          <button onClick={handleSignOut} className="btn-secondary" style={{ padding: "0.5rem" }}>
            Log Out
          </button>
        </div>
      </aside>

      {/* 2. Middle Column: Chat Window */}
      <main style={{ display: "flex", flexDirection: "column", height: "100%", background: "#0c0c0e", overflow: "hidden" }}>
        
        {/* Header */}
        <header style={{ padding: "1.25rem 2rem", borderBottom: "1px solid var(--border-glass)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h3 style={{ color: "white", fontSize: "1rem", fontWeight: 700 }}>Chatbot Assistant</h3>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>ADK 2.0 graph workflow routing</span>
          </div>
        </header>

        {/* Messages */}
        <div 
          ref={chatContainerRef}
          style={{ flex: 1, overflowY: "auto", padding: "2rem", display: "flex", flexDirection: "column", gap: "2rem" }}
        >
          {messages.map((msg) => (
            <div 
              key={msg.id} 
              style={{
                display: "flex",
                gap: "1rem",
                alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                flexDirection: msg.role === "user" ? "row-reverse" : "row",
                maxWidth: "85%",
                alignItems: "flex-start"
              }}
            >
              {/* Avatar */}
              {msg.role === "assistant" ? (
                <div style={{
                  width: "32px",
                  height: "32px",
                  borderRadius: "50%",
                  background: "rgba(59, 130, 246, 0.1)",
                  border: "1px solid rgba(59, 130, 246, 0.2)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0
                }}>
                  <GeminiSparkle />
                </div>
              ) : (
                <UserIcon />
              )}

              {/* Message content */}
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <div 
                  className={msg.role === "user" ? "glass-card" : ""} 
                  style={{
                    padding: msg.role === "user" ? "0.85rem 1.25rem" : "0.25rem 0",
                    background: msg.role === "user" ? "rgba(255, 255, 255, 0.04)" : "transparent",
                    border: msg.role === "user" ? "1px solid rgba(255, 255, 255, 0.06)" : "none",
                    borderRadius: "18px",
                    boxShadow: msg.role === "user" ? "0 4px 12px rgba(0, 0, 0, 0.15)" : "none",
                    color: "var(--text)"
                  }}
                >
                  <div style={{ fontSize: "0.95rem", whiteSpace: "pre-wrap", lineHeight: "1.6" }}>
                    {msg.role === "user" ? msg.content : renderMarkdown(msg.content)}
                  </div>
                </div>
                
                {/* Link to Artifact if message includes one */}
                {msg.artifact && (
                  <div 
                    className="glass-card" 
                    style={{ 
                      padding: "1rem", 
                      marginTop: "0.5rem", 
                      background: "rgba(22, 22, 26, 0.5)", 
                      display: "flex", 
                      flexDirection: "column",
                      gap: "0.75rem",
                      maxWidth: "320px",
                      border: "1px solid rgba(255,255,255,0.06)",
                      boxShadow: "0 8px 32px rgba(0, 0, 0, 0.3)"
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span style={{ fontSize: "1.2rem" }}>
                        {msg.artifact.artifact_type === "presentation" ? "📊" : 
                         msg.artifact.artifact_type === "timeline" ? "📅" : 
                         msg.artifact.artifact_type === "scorecard" ? "📈" : "⚖️"}
                      </span>
                      <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "white" }}>
                        {msg.artifact.title}
                      </span>
                    </div>
                    <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                      Interactive {msg.artifact.artifact_type} visualizer.
                    </div>
                    <button 
                      onClick={() => {
                        setActiveArtifact(msg.artifact);
                        if (msg.artifact.artifact_type === "presentation") setSlideIndex(0);
                      }}
                      className="btn-primary" 
                      style={{ padding: "0.5rem", fontSize: "0.8rem", borderRadius: "8px", width: "100%" }}
                    >
                      Open in Canvas
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Streaming Indicator */}
          {isStreaming && (
            <div 
              style={{
                display: "flex",
                gap: "1rem",
                alignSelf: "flex-start",
                maxWidth: "85%",
                alignItems: "flex-start"
              }}
            >
              <div style={{
                width: "32px",
                height: "32px",
                borderRadius: "50%",
                background: "rgba(59, 130, 246, 0.1)",
                border: "1px solid rgba(59, 130, 246, 0.2)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0
              }}>
                <GeminiSparkle />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <div style={{ padding: "0.25rem 0", color: "var(--text)" }}>
                  <div style={{ fontSize: "0.95rem", color: "white" }}>
                    {streamText ? renderMarkdown(streamText) : "Assistant is thinking..."}
                  </div>
                </div>
              </div>
            </div>
          )}

        </div>

        {/* Input Footer */}
        <footer style={{ padding: "1.5rem 2rem", borderTop: "1px solid var(--border-glass)", background: "transparent" }}>
          {chatError && (
            <div
              style={{
                maxWidth: "800px",
                margin: "0 auto 0.75rem",
                padding: "0.75rem 1rem",
                background: "rgba(239, 68, 68, 0.1)",
                border: "1px solid var(--red)",
                borderRadius: "12px",
                color: "var(--red)",
                fontSize: "0.85rem",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "1rem",
              }}
            >
              <span>{chatError}</span>
              <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
                {lastUserMessage && (
                  <button
                    onClick={() => sendMessage(lastUserMessage)}
                    disabled={isStreaming}
                    className="btn-secondary"
                    style={{ padding: "0.35rem 0.85rem", fontSize: "0.8rem", borderRadius: "8px" }}
                  >
                    Retry
                  </button>
                )}
                <button
                  onClick={() => setChatError("")}
                  style={{ background: "transparent", color: "var(--red)", padding: "0 0.25rem", display: "flex", alignItems: "center" }}
                  aria-label="Dismiss error"
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                    <path d="M3 3L11 11M11 3L3 11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
            </div>
          )}
          <form onSubmit={handleSendMessage} style={{ maxWidth: "800px", margin: "0 auto", display: "flex", gap: "0.75rem", position: "relative" }}>
            <div style={{ flex: 1, position: "relative", display: "flex", alignItems: "center" }}>
              <input 
                type="text" 
                placeholder="Ask about alignment, timelines, or generate a presentation..." 
                value={input} 
                onChange={(e) => setInput(e.target.value)}
                style={{ 
                  width: "100%", 
                  padding: "0.85rem 1.5rem", 
                  paddingRight: "5rem", 
                  borderRadius: "30px", 
                  background: "rgba(22, 22, 26, 0.8)", 
                  border: "1px solid var(--border-glass)",
                  backdropFilter: "blur(24px)",
                  color: "white",
                  fontSize: "0.95rem"
                }}
              />
              <button 
                type="submit" 
                disabled={isStreaming || !input.trim()}
                style={{ 
                  position: "absolute", 
                  right: "6px", 
                  padding: "0.55rem 1.25rem", 
                  borderRadius: "20px", 
                  background: input.trim() ? "var(--accent-gradient)" : "rgba(255,255,255,0.05)",
                  color: input.trim() ? "white" : "rgba(255,255,255,0.3)",
                  fontWeight: 600,
                  fontSize: "0.85rem"
                }}
              >
                Send
              </button>
            </div>
          </form>
        </footer>
      </main>

      {/* 3. Right Column: Persistent Dynamic Canvas */}
      <section className="glass-panel" style={{ padding: "2rem", borderLeft: "1px solid var(--border-glass)", display: "flex", flexDirection: "column", height: "100%", background: "#16161a", overflow: "hidden" }}>
        {activeArtifact ? (
          <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
              <span className="badge" style={{ background: "var(--accent)" }}>
                {activeArtifact.artifact_type.toUpperCase()}
              </span>
              <button 
                onClick={() => setActiveArtifact(null)} 
                style={{ background: "transparent", color: "var(--text-muted)", fontSize: "0.85rem" }}
              >
                Clear Canvas
              </button>
            </div>

            <h2 style={{ fontSize: "1.3rem", fontWeight: 800, color: "white", marginBottom: "1.5rem" }}>
              {activeArtifact.title}
            </h2>

            {/* Dynamic Rendering based on Artifact Type */}
            <div style={{ flex: 1, overflowY: "auto" }}>
              
              {/* Timeline Visualizer */}
              {activeArtifact.artifact_type === "timeline" && (
                <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", position: "relative", paddingLeft: "1.5rem" }}>
                  <div style={{ position: "absolute", left: "4px", top: "8px", bottom: "8px", width: "2px", background: "rgba(255,255,255,0.1)" }} />
                  {activeArtifact.events.map((evt: any) => (
                    <div key={evt.id} style={{ position: "relative" }}>
                      {/* Visual Bullet */}
                      <div 
                        style={{ 
                          position: "absolute", 
                          left: "-23px", 
                          top: "6px", 
                          width: "10px", 
                          height: "10px", 
                          borderRadius: "50%", 
                          background: evt.type === "decision" ? "var(--green)" : "var(--accent)" 
                        }} 
                      />
                      <div className="glass-card" style={{ padding: "1rem", background: "rgba(255,255,255,0.01)" }}>
                        <div style={{ fontSize: "0.75rem", color: "var(--accent)", fontWeight: 700, marginBottom: "0.25rem" }}>
                          {evt.date}
                        </div>
                        <div style={{ fontSize: "0.9rem", fontWeight: 700, color: "white", marginBottom: "0.25rem" }}>
                          {evt.summary}
                        </div>
                        <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                          {evt.details}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Presentation Slide deck */}
              {activeArtifact.artifact_type === "presentation" && (
                <div style={{ height: "100%", display: "flex", flexDirection: "column" }} className="animate-fade-in">
                  <div className="glass-card" style={{ flex: 1, padding: "2rem", display: "flex", flexDirection: "column", justifyContent: "center", background: "rgba(255,255,255,0.01)", minHeight: "300px" }}>
                    <h3 style={{ fontSize: "1.4rem", fontWeight: 800, color: "white", marginBottom: "1rem" }}>
                      {activeArtifact.slides[slideIndex]?.title}
                    </h3>
                    {activeArtifact.slides[slideIndex]?.subtitle && (
                      <h4 style={{ fontSize: "0.9rem", color: "var(--accent)", marginBottom: "1.5rem" }}>
                        {activeArtifact.slides[slideIndex]?.subtitle}
                      </h4>
                    )}
                    
                    {/* Render Bullet points or text */}
                    {activeArtifact.slides[slideIndex]?.bullets && activeArtifact.slides[slideIndex].bullets.length > 0 ? (
                      <ul style={{ display: "flex", flexDirection: "column", gap: "0.75rem", paddingLeft: "1.2rem", color: "var(--text-muted)", fontSize: "0.9rem" }}>
                        {activeArtifact.slides[slideIndex].bullets.map((b: string, bIdx: number) => (
                          <li key={bIdx}>{b}</li>
                        ))}
                      </ul>
                    ) : (
                      <p style={{ color: "var(--text-muted)", fontSize: "0.95rem" }}>
                        {activeArtifact.slides[slideIndex]?.content}
                      </p>
                    )}
                  </div>

                  {/* Navigation Controls */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "1.5rem" }}>
                    <button 
                      className="btn-secondary" 
                      style={{ padding: "0.5rem 1rem" }}
                      disabled={slideIndex === 0}
                      onClick={() => setSlideIndex((prev) => prev - 1)}
                    >
                      Prev
                    </button>
                    <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                      Slide {slideIndex + 1} of {activeArtifact.slides.length}
                    </span>
                    <button 
                      className="btn-secondary" 
                      style={{ padding: "0.5rem 1rem" }}
                      disabled={slideIndex === activeArtifact.slides.length - 1}
                      onClick={() => setSlideIndex((prev) => prev + 1)}
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}

              {/* Scorecard Visualizer */}
              {activeArtifact.artifact_type === "scorecard" && (
                <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }} className="animate-fade-in">
                  {/* Gauge Card */}
                  <div className="glass-card" style={{ padding: "1.5rem", textAlign: "center", background: "rgba(255, 255, 255, 0.01)", border: "1px solid var(--border-glass)" }}>
                    <div style={{ fontSize: "0.85rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, marginBottom: "0.5rem" }}>
                      Reliability Score
                    </div>
                    <div style={{ fontSize: "3rem", fontWeight: 900, color: "var(--green)", textShadow: "0 0 15px rgba(16, 185, 129, 0.3)", lineHeight: 1 }}>
                      {activeArtifact.reliability.toFixed(1)}%
                    </div>
                    {/* Progress Bar */}
                    <div style={{ width: "100%", height: "8px", background: "rgba(255,255,255,0.05)", borderRadius: "4px", marginTop: "1rem", overflow: "hidden" }}>
                      <div style={{ width: `${activeArtifact.reliability}%`, height: "100%", background: "var(--green)", borderRadius: "4px", boxShadow: "0 0 8px var(--green)" }} />
                    </div>
                    <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
                      Calculated from action item completion rate
                    </div>
                  </div>

                  {/* Stats Grid */}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                    <div className="glass-card" style={{ padding: "1rem", background: "rgba(255,255,255,0.01)" }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Completed</div>
                      <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--green)" }}>{activeArtifact.stats.completed}</div>
                    </div>
                    <div className="glass-card" style={{ padding: "1rem", background: "rgba(255,255,255,0.01)" }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Open</div>
                      <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--blue)" }}>{activeArtifact.stats.open}</div>
                    </div>
                    <div className="glass-card" style={{ padding: "1rem", background: "rgba(255,255,255,0.01)" }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Delayed</div>
                      <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--yellow)" }}>{activeArtifact.stats.delayed}</div>
                    </div>
                    <div className="glass-card" style={{ padding: "1rem", background: "rgba(255,255,255,0.01)" }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Abandoned</div>
                      <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--red)" }}>{activeArtifact.stats.abandoned}</div>
                    </div>
                  </div>

                  {/* Top Topics */}
                  {activeArtifact.top_topics && activeArtifact.top_topics.length > 0 && (
                    <div className="glass-card" style={{ padding: "1.25rem", background: "rgba(255,255,255,0.01)" }}>
                      <h4 style={{ fontSize: "0.85rem", color: "white", textTransform: "uppercase", fontWeight: 700, marginBottom: "0.75rem" }}>
                        Key Areas of Focus
                      </h4>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                        {activeArtifact.top_topics.map((t: string, idx: number) => (
                          <span key={idx} className="badge" style={{ background: "rgba(99,102,241,0.15)", color: "var(--accent)", border: "1px solid rgba(99,102,241,0.2)", padding: "0.25rem 0.5rem", borderRadius: "4px", fontSize: "0.75rem" }}>
                            {t}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Key Insights */}
                  {activeArtifact.key_insights && activeArtifact.key_insights.length > 0 && (
                    <div className="glass-card" style={{ padding: "1.25rem", background: "rgba(255,255,255,0.01)" }}>
                      <h4 style={{ fontSize: "0.85rem", color: "white", textTransform: "uppercase", fontWeight: 700, marginBottom: "0.75rem" }}>
                        Qualitative Insights
                      </h4>
                      <ul style={{ paddingLeft: "1.2rem", color: "var(--text-muted)", fontSize: "0.85rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                        {activeArtifact.key_insights.map((insight: string, idx: number) => (
                          <li key={idx}>{insight}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Comparison Visualizer */}
              {activeArtifact.artifact_type === "comparison" && (
                <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }} className="animate-fade-in">
                  {/* Alignment Score Card */}
                  <div className="glass-card" style={{ padding: "1.5rem", background: "rgba(255, 255, 255, 0.01)", border: "1px solid var(--border-glass)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div style={{ textAlign: "left" }}>
                        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>Entity A</div>
                        <div style={{ fontSize: "1rem", fontWeight: 700, color: "white" }}>{activeArtifact.entity_a}</div>
                      </div>
                      <div style={{ textAlign: "center", background: "rgba(99, 102, 241, 0.15)", borderRadius: "50%", width: "80px", height: "80px", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", border: "2px solid var(--accent)", boxShadow: "0 0 15px rgba(99, 102, 241, 0.3)" }}>
                        <div style={{ fontSize: "1.25rem", fontWeight: 800, color: "white" }}>{activeArtifact.alignment_score.toFixed(0)}%</div>
                        <div style={{ fontSize: "0.55rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Align</div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>Entity B</div>
                        <div style={{ fontSize: "1rem", fontWeight: 700, color: "white" }}>{activeArtifact.entity_b}</div>
                      </div>
                    </div>
                    <div style={{ textAlign: "center", fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "1rem" }}>
                      Joint Decisions: <strong>{activeArtifact.joint_decisions}</strong>
                    </div>
                  </div>

                  {/* Contrasting Viewpoints */}
                  {activeArtifact.contrasting_viewpoints && activeArtifact.contrasting_viewpoints.length > 0 && (
                    <div className="glass-card" style={{ padding: "1.25rem", background: "rgba(255,255,255,0.01)" }}>
                      <h4 style={{ fontSize: "0.85rem", color: "white", textTransform: "uppercase", fontWeight: 700, marginBottom: "0.75rem" }}>
                        Contrasting Viewpoints
                      </h4>
                      <ul style={{ paddingLeft: "1.2rem", color: "var(--text-muted)", fontSize: "0.85rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                        {activeArtifact.contrasting_viewpoints.map((pt: string, idx: number) => (
                          <li key={idx}>{pt}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Key Findings */}
                  {activeArtifact.key_findings && activeArtifact.key_findings.length > 0 && (
                    <div className="glass-card" style={{ padding: "1.25rem", background: "rgba(255,255,255,0.01)" }}>
                      <h4 style={{ fontSize: "0.85rem", color: "white", textTransform: "uppercase", fontWeight: 700, marginBottom: "0.75rem" }}>
                        Strategic Key Findings
                      </h4>
                      <ul style={{ paddingLeft: "1.2rem", color: "var(--text-muted)", fontSize: "0.85rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                        {activeArtifact.key_findings.map((f: string, idx: number) => (
                          <li key={idx}>{f}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

            </div>
          </div>
        ) : (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", textAlign: "center", color: "var(--text-muted)" }}>
            <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>🖼️</div>
            <h3 style={{ color: "white", fontSize: "1.1rem", marginBottom: "0.5rem" }}>Empty Canvas</h3>
            <p style={{ fontSize: "0.85rem", maxWidth: "300px" }}>
              Ask the chatbot to analyze data, compile timelines, or build a presentation to see dynamic visual artifacts rendered here.
            </p>
          </div>
        )}
      </section>

    </div>
  );
}
