import { initializeApp, getApps, getApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: "AIzaSyCEeCu8ZszrVva2sS7LNq13fCchpvhhD38",
  authDomain: "meeting-analysis-6c116.firebaseapp.com",
  projectId: "meeting-analysis-6c116",
  storageBucket: "meeting-analysis-6c116.firebasestorage.app",
  messagingSenderId: "33229996475",
  appId: "1:33229996475:web:257770266444b90fd9049e"
};

// Initialize Firebase (SSR-safe singleton)
const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApp();
const auth = getAuth(app);
const db = getFirestore(app);

export { app, auth, db };
