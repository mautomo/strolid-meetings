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

  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  
  let currentList: React.ReactNode[] = [];
  let currentListType: "ul" | "ol" | null = null;
  
  let currentTableHeaders: string[] = [];
  let currentTableRows: string[][] = [];
  let inTable = false;
  
  const parseInline = (str: string): React.ReactNode[] => {
    const parts = str.split(/(\*\*.*?\*\*)/g);
    return parts.map((part, idx) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={idx}>{part.slice(2, -2)}</strong>;
      }
      return part;
    });
  };

  const flushList = (key: number) => {
    if (currentList.length > 0) {
      if (currentListType === "ul") {
        elements.push(
          <ul key={`ul-${key}`} style={{ paddingLeft: "1.25rem", margin: "0.5rem 0", listStyleType: "disc" }}>
            {currentList}
          </ul>
        );
      } else {
        elements.push(
          <ol key={`ol-${key}`} style={{ paddingLeft: "1.25rem", margin: "0.5rem 0", listStyleType: "decimal" }}>
            {currentList}
          </ol>
        );
      }
      currentList = [];
      currentListType = null;
    }
  };

  const flushTable = (key: number) => {
    if (inTable) {
      elements.push(
        <div key={`table-wrapper-${key}`} className="table-container">
          <table className="markdown-table">
            <thead>
              <tr>
                {currentTableHeaders.map((header, hIdx) => (
                  <th key={hIdx}>{parseInline(header)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {currentTableRows.map((row, rIdx) => (
                <tr key={rIdx}>
                  {row.map((cell, cIdx) => (
                    <td key={cIdx}>{parseInline(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      currentTableHeaders = [];
      currentTableRows = [];
      inTable = false;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed.startsWith("|")) {
      flushList(i);
      const cells = line.split("|").slice(1, -1).map(c => c.trim());
      const isSeparator = cells.every(c => /^:?-+:?$/.test(c));
      
      if (isSeparator) {
        continue;
      }
      
      if (!inTable) {
        inTable = true;
        currentTableHeaders = cells;
      } else {
        currentTableRows.push(cells);
      }
      continue;
    } else if (inTable) {
      flushTable(i);
    }

    const bulletMatch = line.match(/^(\s*)([-*+])\s+(.*)/);
    const numberedMatch = line.match(/^(\s*)(\d+)\.\s+(.*)/);

    if (bulletMatch) {
      if (currentListType !== "ul") {
        flushList(i);
        currentListType = "ul";
      }
      currentList.push(
        <li key={`li-${i}`} style={{ marginBottom: "0.2rem" }}>
          {parseInline(bulletMatch[3])}
        </li>
      );
      continue;
    } else if (numberedMatch) {
      if (currentListType !== "ol") {
        flushList(i);
        currentListType = "ol";
      }
      currentList.push(
        <li key={`li-${i}`} style={{ marginBottom: "0.2rem" }}>
          {parseInline(numberedMatch[3])}
        </li>
      );
      continue;
    }

    if (trimmed === "") {
      flushList(i);
      elements.push(<div key={`space-${i}`} style={{ height: "0.5rem" }} />);
      continue;
    }

    flushList(i);
    elements.push(
      <p key={`p-${i}`} style={{ margin: "0.25rem 0", lineHeight: "1.4" }}>
        {parseInline(line)}
      </p>
    );
  }

  flushList(lines.length);
  flushTable(lines.length);

  return <>{elements}</>;
}

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
  


  // Dynamic Meetings and Stats state
  const [meetings, setMeetings] = useState<any[]>([]);
  const [stats, setStats] = useState({ meetings_count: 53, decisions_count: 225 });

  // Artifact View State
  const [activeArtifact, setActiveArtifact] = useState<any>(null);
  const [slideIndex, setSlideIndex] = useState(0);

  // Recaptcha for Phone Auth
  const recaptchaVerifierRef = useRef<any>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

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
          setMeetings(meetingsData.meetings || []);
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
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
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

  // Send message to FastAPI ADK Chatbot
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;

    const userMsgText = input;
    setInput("");
    setIsStreaming(true);
    setStreamText("");

    try {
      const token = await user.getIdToken();
      const headers: Record<string, string> = { 
        "Content-Type": "application/json",
        "x-firebase-auth": token
      };

      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: headers,
        body: JSON.stringify({
          session_id: sessionId,
          user_id: user?.uid || "anonymous",
          message: userMsgText
        })
      });

      if (!response.ok) throw new Error("API request failed.");

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error("Stream reader not supported.");

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        setStreamText((prev) => prev + chunk);
      }
    } catch (err) {
      console.error("Chat error:", err);
    } finally {
      setIsStreaming(false);
      setStreamText("");
    }
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
      <aside className="glass-panel" style={{ padding: "1.5rem", display: "flex", flexDirection: "column", borderRight: "1px solid var(--border-glass)" }}>
        <div style={{ marginBottom: "2rem" }}>
          <h2 style={{ fontSize: "1.2rem", fontWeight: 800, color: "white", marginBottom: "0.25rem" }}>Strolid Hub</h2>
          <span style={{ fontSize: "0.75rem", color: "var(--accent)", fontWeight: 700 }}>MEETING INTELLIGENCE v2.0</span>
        </div>

        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div>
            <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>Select Session / Meeting</label>
            <select 
              value={sessionId} 
              onChange={(e) => setSessionId(e.target.value)} 
              style={{ width: "100%", marginTop: "0.4rem" }}
            >
              <optgroup label="Global Sessions">
                <option value="session-strolid-q4-2025">Vinnie & Michael Sync (Q4 2025)</option>
                <option value="session-leadership-overall">Leadership Meetings (2025-2026)</option>
              </optgroup>
              <optgroup label="Individual Meetings">
                {meetings.map((m) => (
                  <option key={m.meeting_id} value={`session-meeting-${m.meeting_id}`}>
                    {m.date} - {m.title || m.meeting_id}
                  </option>
                ))}
              </optgroup>
            </select>
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
      <main style={{ display: "flex", flexDirection: "column", height: "100%", background: "#090d16" }}>
        
        {/* Header */}
        <header style={{ padding: "1.25rem 2rem", borderBottom: "1px solid var(--border-glass)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h3 style={{ color: "white", fontSize: "1rem", fontWeight: 700 }}>Chatbot Assistant</h3>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>ADK 2.0 graph workflow routing</span>
          </div>
        </header>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: "auto", padding: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          {messages.map((msg) => (
            <div 
              key={msg.id} 
              style={{
                alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                maxWidth: "80%"
              }}
            >
              <div 
                className="glass-card" 
                style={{
                  padding: "1rem 1.25rem",
                  background: msg.role === "user" ? "var(--accent)" : "rgba(31, 41, 55, 0.5)",
                  borderColor: msg.role === "user" ? "var(--accent)" : "rgba(255, 255, 255, 0.05)",
                  borderRadius: msg.role === "user" ? "16px 16px 2px 16px" : "16px 16px 16px 2px"
                }}
              >
                <div style={{ fontSize: "0.95rem", whiteSpace: msg.role === "user" ? "pre-wrap" : "normal", color: "white" }}>
                  {msg.role === "user" ? msg.content : renderMarkdown(msg.content)}
                </div>
                
                {/* Link to Artifact if message includes one */}
                {msg.artifact && (
                  <div style={{ marginTop: "1rem", paddingTop: "0.75rem", borderTop: "1px solid rgba(255,255,255,0.1)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                      Generated {msg.artifact.artifact_type}
                    </span>
                    <button 
                      onClick={() => {
                        setActiveArtifact(msg.artifact);
                        if (msg.artifact.artifact_type === "presentation") setSlideIndex(0);
                      }}
                      className="btn-primary" 
                      style={{ padding: "0.25rem 0.75rem", fontSize: "0.75rem", borderRadius: "4px" }}
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
            <div style={{ alignSelf: "flex-start", maxWidth: "80%" }}>
              <div className="glass-card" style={{ padding: "1rem 1.25rem", background: "rgba(31, 41, 55, 0.5)", borderRadius: "16px 16px 16px 2px" }}>
                <div style={{ fontSize: "0.95rem", color: "white" }}>
                  {streamText ? renderMarkdown(streamText) : "Assistant is thinking..."}
                </div>
              </div>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* Input Footer */}
        <footer style={{ padding: "1.5rem 2rem", borderTop: "1px solid var(--border-glass)" }}>
          <form onSubmit={handleSendMessage} style={{ display: "flex", gap: "1rem" }}>
            <input 
              type="text" 
              placeholder="Ask about alignment, timelines, or generate a presentation..." 
              value={input} 
              onChange={(e) => setInput(e.target.value)}
              style={{ flex: 1, fontSize: "0.95rem" }}
            />
            <button type="submit" className="btn-primary" disabled={isStreaming}>
              Send
            </button>
          </form>
        </footer>
      </main>

      {/* 3. Right Column: Persistent Dynamic Canvas */}
      <section className="glass-panel" style={{ padding: "2rem", borderLeft: "1px solid var(--border-glass)", display: "flex", flexDirection: "column", height: "100%", background: "#070b12" }}>
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
                <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
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
