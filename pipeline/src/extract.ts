import { GoogleGenerativeAI } from "@google/generative-ai";
import * as mammoth from "mammoth";
import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtractedMeeting } from "./types.js";

const MEETINGS_DIR = path.resolve(import.meta.dirname, "../../");
const OUTPUT_DIR = path.resolve(import.meta.dirname, "../data/extracted");

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY!);
const model = genAI.getGenerativeModel({ model: "gemini-2.0-flash" });

// Files that are strategy docs, not meetings
const EXCLUDE_FILES = [
  "9 FAQs_ Why Dealers Should Consider Strolid.docx",
  "Jake and Link Marketing Hooks.docx",
  "Marketing hooks 2 more about people.docx",
  "Marketing hooks 3.docx",
  "New marketing hooks.docx",
  "Sophia Outbound and Service inbound Plan.docx",
  "Strolid Website.docx",
  "Website Additions, subtractions and changes.docx",
  "README.md",
];

const EXTRACTION_PROMPT = `You are a meeting intelligence analyst. Extract structured data from this meeting transcript/notes.

Return ONLY valid JSON matching this exact schema (no markdown, no commentary):

{
  "meetingId": "<kebab-case-id from title and date>",
  "title": "<meeting title>",
  "date": "<YYYY-MM-DD>",
  "series": "<recurring series name if applicable, otherwise the meeting title>",
  "type": "<one of: leadership, marketing, product, one-on-one, standup, strategy, other>",
  "attendees": ["<Full Name>", ...],
  "summary": "<2-3 sentence summary of what was discussed and decided>",
  "decisions": [
    {
      "description": "<what was decided>",
      "decidedBy": ["<who made/drove the decision>"],
      "topic": "<kebab-case topic label>",
      "confidence": "<firm|tentative|exploratory>"
    }
  ],
  "actionItems": [
    {
      "task": "<what needs to be done>",
      "owner": "<who is responsible>",
      "deadline": "<YYYY-MM-DD if mentioned, null otherwise>",
      "expectedOutcome": {
        "system": "<where evidence would appear: website, crm, codebase, google-docs, email, slack, calendar, other>",
        "description": "<what the completed outcome looks like>"
      }
    }
  ],
  "topicsDiscussed": ["<kebab-case-topic>", ...],
  "tensions": ["<any disagreements, concerns raised, or unresolved debates>"],
  "referencesToPast": ["<any mentions of previous meetings, past decisions, or historical context>"]
}

Rules:
- Extract ALL decisions, even small ones. A decision is any commitment, agreement, or direction set.
- For attendees, use full names. If only first names are used, include what's available.
- "confidence" should be "firm" if explicitly agreed, "tentative" if conditionally agreed, "exploratory" if just discussed.
- For action items, always try to identify an owner. If no owner is clear, use "Unassigned".
- Topics should be consistent kebab-case labels that could be reused across meetings (e.g., "website-refresh", "messaging-strategy", "buyer-targeting").
- Tensions include any pushback, disagreement, concern, or unresolved debate.
- referencesToPast includes any mention of prior meetings, earlier decisions, or "we discussed this before" type references.
- If the meeting notes include a transcript section, extract from BOTH the summary/details AND the transcript.
- Return valid JSON only. No markdown fencing.`;

function classifyMeetingType(filename: string): ExtractedMeeting["type"] {
  const lower = filename.toLowerCase();
  if (lower.includes("leadership")) return "leadership";
  if (lower.includes("marketing") || lower.includes("vconic"))
    return "marketing";
  if (lower.includes("product") || lower.includes("roadmap")) return "product";
  if (
    lower.includes("1-on-1") ||
    lower.includes("1 on 1") ||
    lower.includes("joe and michael") ||
    lower.includes("michael _") ||
    lower.includes("_ michael") ||
    lower.includes("vin and michael") ||
    lower.includes("call with michael") ||
    lower.includes("michael and vin")
  )
    return "one-on-one";
  if (lower.includes("standup") || lower.includes("scrum")) return "standup";
  if (
    lower.includes("planning") ||
    lower.includes("prioritization") ||
    lower.includes("alignment")
  )
    return "strategy";
  return "other";
}

async function extractTextFromDocx(filePath: string): Promise<string> {
  const buffer = fs.readFileSync(filePath);
  const result = await mammoth.extractRawText({ buffer });
  return result.value;
}

async function extractMeetingData(
  text: string,
  filename: string,
): Promise<ExtractedMeeting> {
  const meetingType = classifyMeetingType(filename);

  const prompt = `${EXTRACTION_PROMPT}\n\nHint: This appears to be a "${meetingType}" type meeting based on the filename: "${filename}"\n\nMeeting notes:\n\n${text}`;

  const result = await model.generateContent(prompt);
  const response = result.response;
  const responseText = response.text();

  // Strip markdown fencing if present
  let jsonText = responseText.trim();
  if (jsonText.startsWith("```")) {
    jsonText = jsonText.replace(/^```(?:json)?\n?/, "").replace(/\n?```$/, "");
  }

  try {
    return JSON.parse(jsonText) as ExtractedMeeting;
  } catch (e) {
    console.error(
      `Failed to parse JSON for ${filename}:`,
      jsonText.slice(0, 200),
    );
    throw e;
  }
}

async function main() {
  // Ensure output directory exists
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  // Get all meeting files
  const allFiles = fs.readdirSync(MEETINGS_DIR);
  const meetingFiles = allFiles.filter(
    (f) =>
      (f.endsWith(".docx") ||
        (f.endsWith(".md") && f.includes("Notes by Gemini"))) &&
      !EXCLUDE_FILES.includes(f),
  );

  console.log(`Found ${meetingFiles.length} meeting files to process.\n`);

  // Check which files have already been extracted
  const existingOutputs = new Set(
    fs.readdirSync(OUTPUT_DIR).map((f) => f.replace(".json", "")),
  );

  const toProcess = meetingFiles.filter((f) => {
    const id = f.replace(/\.[^.]+$/, "");
    return !existingOutputs.has(id);
  });

  if (toProcess.length === 0) {
    console.log("All files already extracted. Use --force to re-extract.");
    if (process.argv.includes("--force")) {
      toProcess.push(...meetingFiles);
      console.log(`Force mode: re-extracting all ${toProcess.length} files.`);
    } else {
      return;
    }
  }

  console.log(`Processing ${toProcess.length} new files...\n`);

  // Process in batches of 3 to respect rate limits
  const BATCH_SIZE = 3;
  let processed = 0;
  let failed = 0;

  for (let i = 0; i < toProcess.length; i += BATCH_SIZE) {
    const batch = toProcess.slice(i, i + BATCH_SIZE);

    const results = await Promise.allSettled(
      batch.map(async (filename) => {
        const filePath = path.join(MEETINGS_DIR, filename);
        const outputId = filename.replace(/\.[^.]+$/, "");
        const outputPath = path.join(OUTPUT_DIR, `${outputId}.json`);

        console.log(`  Extracting: ${filename}`);

        let text: string;
        if (filename.endsWith(".md")) {
          text = fs.readFileSync(filePath, "utf-8");
        } else {
          text = await extractTextFromDocx(filePath);
        }

        // Truncate very long transcripts to avoid token limits
        if (text.length > 50000) {
          console.log(
            `    Truncating ${filename} from ${text.length} to 50000 chars`,
          );
          text =
            text.slice(0, 50000) +
            "\n\n[TRUNCATED - remaining transcript omitted]";
        }

        const data = await extractMeetingData(text, filename);
        fs.writeFileSync(outputPath, JSON.stringify(data, null, 2));
        return data;
      }),
    );

    for (const result of results) {
      if (result.status === "fulfilled") {
        processed++;
      } else {
        failed++;
        console.error(`  FAILED:`, result.reason?.message || result.reason);
      }
    }

    console.log(
      `  Progress: ${processed + failed}/${toProcess.length} (${failed} failed)\n`,
    );
  }

  console.log(
    `\nExtraction complete: ${processed} succeeded, ${failed} failed.`,
  );
  console.log(`Output: ${OUTPUT_DIR}`);
}

main().catch(console.error);
