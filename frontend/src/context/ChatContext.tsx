"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { User } from "firebase/auth";
import { onAuthStateChanged, signOut } from "firebase/auth";
import { collection, query, orderBy, onSnapshot } from "firebase/firestore";
import { auth, db } from "@/lib/firebase";
import {
  createConversation,
  fetchMe,
  fetchMeetings,
  fetchStats,
  fetchTopics,
  listConversations,
  streamChat,
} from "@/lib/api";
import type {
  Artifact,
  CanvasHint,
  Conversation,
  Meeting,
  Message,
  Role,
  Scope,
  SentimentMode,
  Stats,
  Topic,
} from "@/lib/types";

export type SidebarPanel = null | "history" | "scope" | "admin" | "settings";

interface ChatContextValue {
  // Auth
  user: User | null;
  authLoading: boolean;
  signOutUser: () => Promise<void>;
  currentRole: Role;
  allowlistEnforced: boolean;

  // Conversations / scope
  activeConversationId: string | null;
  conversations: Conversation[];
  isOwnerOfActive: boolean;
  newChat: () => Promise<void>;
  selectConversation: (id: string) => void;
  refreshConversations: () => Promise<void>;
  startDate: string;
  endDate: string;
  setStartDate: (v: string) => void;
  setEndDate: (v: string) => void;
  selectedMeetingIds: string[];
  setSelectedMeetingIds: (v: string[]) => void;
  meetings: Meeting[];
  stats: Stats;

  // Tool drawer
  topicsList: Topic[];
  selectedTopics: string[];
  setSelectedTopics: (v: string[]) => void;
  canvasHint: CanvasHint | null;
  setCanvasHint: (v: CanvasHint | null) => void;
  sentimentMode: SentimentMode | null;
  setSentimentMode: (v: SentimentMode | null) => void;

  // Chat
  messages: Message[];
  input: string;
  setInput: (v: string) => void;
  isStreaming: boolean;
  streamText: string;
  chatError: string;
  dismissError: () => void;
  sendMessage: (text: string) => Promise<void>;
  retryLast: () => void;

  // Canvas
  activeArtifact: Artifact | null;
  setActiveArtifact: (a: Artifact | null) => void;
  slideIndex: number;
  setSlideIndex: (n: number) => void;

  // Shell
  activePanel: SidebarPanel;
  setActivePanel: (p: SidebarPanel) => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export function useChat(): ChatContextValue {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used within ChatProvider");
  return ctx;
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [currentRole, setCurrentRole] = useState<Role>("user");
  const [allowlistEnforced, setAllowlistEnforced] = useState(false);

  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [selectedMeetingIds, setSelectedMeetingIds] = useState<string[]>([]);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [stats, setStats] = useState<Stats>({ meetings_count: 53, decisions_count: 225 });
  const [topicsList, setTopicsList] = useState<Topic[]>([]);
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);
  const [canvasHint, setCanvasHint] = useState<CanvasHint | null>(null);
  const [sentimentMode, setSentimentMode] = useState<SentimentMode | null>(null);

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [chatError, setChatError] = useState("");
  const [lastUserMessage, setLastUserMessage] = useState("");

  const [activeArtifact, setActiveArtifact] = useState<Artifact | null>(null);
  const [slideIndex, setSlideIndex] = useState(0);
  const [activePanel, setActivePanel] = useState<SidebarPanel>(null);

  const uniqueMeetings = useMemo(
    () => Array.from(new Map(meetings.map((m) => [m.meeting_id, m])).values()),
    [meetings],
  );

  // Auth state
  useEffect(() => {
    const unsub = onAuthStateChanged(auth, (u) => {
      setUser(u);
      setAuthLoading(false);
    });
    return () => unsub();
  }, []);

  // Reference data + conversations once authenticated.
  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const token = await user.getIdToken();
        const [ms, st, tp, me, convs] = await Promise.all([
          fetchMeetings(token),
          fetchStats(token),
          fetchTopics(token),
          fetchMe(token),
          listConversations(token),
        ]);
        setMeetings(ms);
        if (st) setStats(st);
        setTopicsList(tp);
        if (me) {
          setCurrentRole(me.role);
          setAllowlistEnforced(me.allowlist_enforced);
        }
        setConversations(convs);
        if (convs.length > 0) {
          const first = convs[0];
          setActiveConversationId(first.id);
          setStartDate(first.scope?.startDate || "");
          setEndDate(first.scope?.endDate || "");
          setSelectedMeetingIds(first.scope?.meetingIds || []);
          setSelectedTopics(first.scope?.topics || []);
        } else {
          const id = await createConversation(token);
          setActiveConversationId(id);
          setConversations(await listConversations(token));
        }
      } catch (err) {
        console.error("Failed to initialize session:", err);
      }
    })();
  }, [user]);

  // Firestore messages for the active conversation. Stale canvas/error are cleared in
  // selectConversation/newChat, keeping this effect subscription-only (no synchronous
  // setState in the body). Security rules gate reads to the owner or shared users.
  useEffect(() => {
    if (!user || !db || !activeConversationId) return;

    const msgsRef = collection(db, "conversations", activeConversationId, "messages");
    const q = query(msgsRef, orderBy("timestamp", "asc"));
    const unsub = onSnapshot(
      q,
      (snapshot) => {
        const msgs: Message[] = [];
        snapshot.forEach((doc) => {
          const data = doc.data();
          msgs.push({
            id: doc.id,
            role: data.role,
            content: data.content,
            artifact: data.artifact,
            timestamp: data.timestamp,
          });
        });
        setMessages(msgs);
        const last = msgs[msgs.length - 1];
        if (last?.artifact) {
          setActiveArtifact(last.artifact);
          if (last.artifact.artifact_type === "presentation") setSlideIndex(0);
        }
      },
      (err) => console.error("Message listener error:", err),
    );
    return () => unsub();
  }, [user, activeConversationId]);

  const applyScope = (scope?: Scope) => {
    setStartDate(scope?.startDate || "");
    setEndDate(scope?.endDate || "");
    setSelectedMeetingIds(scope?.meetingIds || []);
    setSelectedTopics(scope?.topics || []);
  };

  const refreshConversations = async () => {
    if (!user) return;
    try {
      const token = await user.getIdToken();
      setConversations(await listConversations(token));
    } catch (err) {
      console.error("Failed to refresh conversations:", err);
    }
  };

  const newChat = async () => {
    if (!user) return;
    setActiveArtifact(null);
    setChatError("");
    setMessages([]);
    applyScope(undefined);
    try {
      const token = await user.getIdToken();
      const id = await createConversation(token);
      setActiveConversationId(id);
      await refreshConversations();
      setActivePanel(null);
    } catch (err) {
      console.error("Failed to start a new chat:", err);
    }
  };

  const selectConversation = (id: string) => {
    setActiveArtifact(null);
    setChatError("");
    setMessages([]);
    applyScope(conversations.find((c) => c.id === id)?.scope);
    setActiveConversationId(id);
    setActivePanel(null);
  };

  const activeConversation = conversations.find((c) => c.id === activeConversationId);
  const isOwnerOfActive = activeConversation ? activeConversation.isOwner : true;

  const sendMessage = async (text: string) => {
    if (!text.trim() || isStreaming || !user || !activeConversationId) return;
    if (!isOwnerOfActive) {
      setChatError("This conversation was shared with you read-only. Start a new chat to ask your own questions.");
      return;
    }
    if (startDate && endDate && startDate > endDate) {
      setChatError("Start date must be on or before the end date.");
      return;
    }
    setChatError("");
    setLastUserMessage(text);
    setIsStreaming(true);
    setStreamText("");

    try {
      const token = await user.getIdToken();
      await streamChat(
        token,
        {
          session_id: activeConversationId,
          user_id: user.uid || "anonymous",
          message: text,
          start_date: startDate || null,
          end_date: endDate || null,
          selected_meeting_ids: selectedMeetingIds.length > 0 ? selectedMeetingIds : null,
          topics: selectedTopics.length > 0 ? selectedTopics : null,
          canvas_hint: canvasHint,
          sentiment_mode: sentimentMode,
        },
        {
          onToken: (delta) => setStreamText((prev) => prev + delta),
          onArtifact: (payload) => {
            setActiveArtifact(payload);
            if (payload.artifact_type === "presentation") setSlideIndex(0);
          },
          onError: (message) => setChatError(message),
        },
      );
    } finally {
      setIsStreaming(false);
      setStreamText("");
      // canvas_hint and sentiment_mode are one-shot routing hints; clear after each send.
      setCanvasHint(null);
      setSentimentMode(null);
      // The backend may have created the conversation or set its title; refresh the list.
      void refreshConversations();
    }
  };

  const value: ChatContextValue = {
    user,
    authLoading,
    signOutUser: () => signOut(auth),
    currentRole,
    allowlistEnforced,
    activeConversationId,
    conversations,
    isOwnerOfActive,
    newChat,
    selectConversation,
    refreshConversations,
    startDate,
    endDate,
    setStartDate,
    setEndDate,
    selectedMeetingIds,
    setSelectedMeetingIds,
    meetings: uniqueMeetings,
    stats,
    topicsList,
    selectedTopics,
    setSelectedTopics,
    canvasHint,
    setCanvasHint,
    sentimentMode,
    setSentimentMode,
    messages,
    input,
    setInput,
    isStreaming,
    streamText,
    chatError,
    dismissError: () => setChatError(""),
    sendMessage,
    retryLast: () => {
      if (lastUserMessage) void sendMessage(lastUserMessage);
    },
    activeArtifact,
    setActiveArtifact,
    slideIndex,
    setSlideIndex,
    activePanel,
    setActivePanel,
  };

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}
