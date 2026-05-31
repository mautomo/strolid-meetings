"use client";

import { useRef, useState } from "react";
import {
  signInWithEmailAndPassword,
  signInWithPhoneNumber,
  RecaptchaVerifier,
  GoogleAuthProvider,
  signInWithPopup,
  type ConfirmationResult,
} from "firebase/auth";
import { AlertCircle } from "lucide-react";
import { auth } from "@/lib/firebase";

type Mode = "email" | "phone";

export function LoginScreen() {
  const [mode, setMode] = useState<Mode>("email");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [confirmation, setConfirmation] = useState<ConfirmationResult | null>(null);
  const [error, setError] = useState("");
  const recaptchaRef = useRef<RecaptchaVerifier | null>(null);

  const onEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await signInWithEmailAndPassword(auth, email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Email authentication failed.");
    }
  };

  const onGoogle = async () => {
    setError("");
    try {
      await signInWithPopup(auth, new GoogleAuthProvider());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google authentication failed.");
    }
  };

  const setupRecaptcha = () => {
    if (recaptchaRef.current) return;
    recaptchaRef.current = new RecaptchaVerifier(auth, "recaptcha-container", { size: "invisible" });
  };

  const onSendCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setupRecaptcha();
    try {
      setConfirmation(await signInWithPhoneNumber(auth, phone, recaptchaRef.current!));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send verification SMS.");
    }
  };

  const onVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!confirmation) return;
    setError("");
    try {
      await confirmation.confirm(code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid SMS verification code.");
    }
  };

  const tab = (m: Mode, label: string) => (
    <button
      type="button"
      className={mode === m ? "btn btn-secondary" : "btn btn-ghost"}
      style={{ flex: 1, height: 38 }}
      onClick={() => {
        setMode(m);
        setError("");
      }}
    >
      {label}
    </button>
  );

  return (
    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", padding: "1rem" }}>
      <div className="card-premium" style={{ width: "100%", maxWidth: 420, padding: "2.5rem" }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/images/brand/vandoko-wordmark-transparent-white.png"
          alt="Vandoko"
          style={{ height: 28, display: "block", margin: "0 auto 0.5rem" }}
        />
        <p className="t-sm" style={{ textAlign: "center", marginBottom: "1.75rem" }}>
          Meeting Intelligence
        </p>

        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
          {tab("email", "Email")}
          {tab("phone", "Phone")}
        </div>

        {error && (
          <div
            style={{
              display: "flex",
              gap: "0.5rem",
              alignItems: "flex-start",
              padding: "0.75rem",
              background: "rgba(208, 14, 17, 0.08)",
              border: "1px solid var(--destructive)",
              borderRadius: "var(--radius-base)",
              color: "var(--destructive)",
              fontSize: "0.82rem",
              marginBottom: "1rem",
            }}
          >
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>{error}</span>
          </div>
        )}

        {mode === "email" ? (
          <form onSubmit={onEmail} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <Field label="Email address">
              <input type="email" placeholder="you@domain.com" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="Password">
              <input type="password" placeholder="Password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <button type="submit" className="btn btn-primary" style={{ marginTop: "0.25rem" }}>
              Sign in
            </button>
          </form>
        ) : !confirmation ? (
          <form onSubmit={onSendCode} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <Field label="Phone number (international)">
              <input type="tel" placeholder="+15551234567" required value={phone} onChange={(e) => setPhone(e.target.value)} />
            </Field>
            <div id="recaptcha-container" />
            <button type="submit" className="btn btn-primary">
              Send verification SMS
            </button>
          </form>
        ) : (
          <form onSubmit={onVerify} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <Field label="6-digit SMS code">
              <input type="text" placeholder="123456" required value={code} onChange={(e) => setCode(e.target.value)} />
            </Field>
            <button type="submit" className="btn btn-primary">
              Verify and continue
            </button>
          </form>
        )}

        <div style={{ margin: "1.5rem 0", display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
          <span className="t-sm">or</span>
          <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
        </div>

        <button type="button" className="btn btn-outline" style={{ width: "100%" }} onClick={onGoogle}>
          Continue with Google
        </button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
      <label className="t-xs" style={{ letterSpacing: "0.08em" }}>
        {label}
      </label>
      {children}
    </div>
  );
}
