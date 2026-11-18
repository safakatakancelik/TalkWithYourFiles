# Architecture & Workflow Diagrams

This directory is the single source of truth for all system architecture, workflow, and sequence diagrams for **Talk With Your Files**.

## Table of Diagrams

1. [End-to-End Pipeline (Ingestion, Search, Agents, Verification)](#1-end-to-end-pipeline)
2. [System Components & Architecture](#2-system-components--architecture)
3. [Question Orchestration Sequence](#3-question-orchestration-sequence)
4. [File Ingestion Flow](#4-file-ingestion-flow)
5. [Question State Machine](#5-question-state-machine)
6. [Runtime Execution Modes](#6-runtime-execution-modes)

---

## 1. End-to-End Pipeline

How documents are ingested, stored, indexed, retrieved, and answered through the multi-agent huddle and verification loop:

```mermaid
flowchart TD
    subgraph INGEST["1. Data Ingestion & Storage Pipeline"]
        Upload["Document Upload / Add Version<br/>(upload_file / add_file_version)"] --> Store["Content-Addressed Store<br/>~/.twyf/files/ab/abcdef..."]
        Store --> Verify["Integrity & Availability Check<br/>(verify content sha256)"]
        Verify --> Parse["Parser<br/>(Docling layout & OCR, or basic pypdf/docx/csv/md/txt)"]
        Parse --> Norm["Text Normalization<br/>(Unicode NFKC, straight quotes, whitespace)"]
        Norm --> Extract["Extractions & Blocks<br/>(canonical text, page, bbox, char_start/end)"]
        Extract --> Chunk["Block-Aligned Chunker<br/>(1200 char window, block overlap)"]
        Chunk --> ChunksDB[("SQLite: chunks<br/>(exact char offsets in canonical text)")]

        ChunksDB --> FTS[("SQLite FTS5: chunks_fts<br/>(BM25 keyword index)")]
        ChunksDB --> FastEmbed["FastEmbed (bge-small-en-v1.5)<br/>batch of 64 chunks"]
        FastEmbed --> VecDB[("SQLite: chunk_embeddings<br/>(float32 BLOBs via sqlite-vec / numpy)")]

        ChunksDB --> FirstRead["first_read agent turn<br/>(summary note & citations)"]
        FirstRead --> NotesDB[("SQLite: notes & note_embeddings<br/>(summaries, findings, interpretations)")]
    end

    subgraph RETRIEVAL["2. Query Processing & Hybrid Retrieval"]
        User["User Prompt / Query<br/>(Chat UI, API, or MCP Harness)"] --> Orchestrator["Orchestrator: plan & assign<br/>(selects translators, files, focus)"]
        Orchestrator --> WorkTurn["Translator: work turn<br/>(requests passages for assigned files)"]
        WorkTurn --> Hybrid["HybridRetriever<br/>(query = question + focus)"]

        FTS -. "filter: v_usable_files (current version)" .-> KeywordSearch["Keyword Search<br/>chunks_fts (BM25)"]
        VecDB -. "filter: v_usable_files (current version)" .-> VectorSearch["Vector Search<br/>chunk_embeddings (Cosine Sim)"]

        Hybrid --> KeywordSearch
        Hybrid --> VectorSearch
        KeywordSearch --> RRF["Reciprocal Rank Fusion (RRF)<br/>score = sum(1 / (60 + rank))"]
        VectorSearch --> RRF

        NotesDB -. "passage_boost(note_weights)" .-> WeightBoost["Note Weight Multiplier<br/>(boost passages cited by high notes)"]
        RRF --> WeightBoost
        WeightBoost --> TopPassages["Top K Passages<br/>(fixed window: 8 passages, exact offsets)"]
    end

    subgraph AGENTS["3. Multi-Agent Verification & Response"]
        TopPassages --> TranslatorAction["Translator Reads Passages<br/>(proposes statements with verbatim quotes)"]
        TranslatorAction --> QuoteCheck{"Mechanical Quote Check<br/>(exact substring in canonical text?)"}
        QuoteCheck -- "No" --> TurnRetry["Reject & Retry Turn<br/>(up to TWYF_MAX_TURN_RETRIES)"]
        TurnRetry --> TranslatorAction
        QuoteCheck -- "Yes" --> OrchReview["Orchestrator: review turn<br/>(discussion: continue or settle)"]

        OrchReview --> DraftClaims["Orchestrator: draft_claims<br/>(drafts checkable claims citing passages)"]
        DraftClaims --> Verifier["Verifier: verify turn<br/>(judges claims against cited passages)"]

        Verifier --> Verdict{"All claims supported?"}
        Verdict -- "No (rounds left)" --> OrchReview
        Verdict -- "Yes / rounds exhausted" --> ChatAgent["Chat Agent: write_answer<br/>(drafts answer from verified claims only)"]
        ChatAgent --> FinalResponse["Final Answer with Exact Citations"]
        FinalResponse --> UserResponse["Return Verified Answer to User"]
    end
```

---

## 2. System Components & Architecture

The relationship between client interfaces, backend services, local storage, agent runtimes, and instructions:

```mermaid
flowchart LR
    subgraph Clients
        UI["Chat UI<br/>(React, frontend/)"]
        Harness["AI harness<br/>(Claude Code, Codex, ...)"]
        Script["Scripts, curl,<br/>/docs page"]
    end

    subgraph Backend["Backend (backend/src/twyf)"]
        MCP["MCP server<br/>twyf mcp"]
        HTTP["HTTP API + event streams<br/>twyf serve"]
        Ops["Operation list<br/>contract/operations.py"]
        Services["Services<br/>(the rules)"]
        Engine["Orchestration engine<br/>+ state machine"]
        Runner["Turn runner<br/>validate, check quotes, retry"]
        Ingest["Ingestion<br/>parse, chunk, index, embed"]
        Retrieval["Retrieval<br/>keyword + vector, fused"]
        Recorder["Recorder<br/>event log + broker"]
    end

    subgraph Storage["~/.twyf"]
        DB[("SQLite<br/>tables, FTS5, sqlite-vec,<br/>history, app_events")]
        Files[("files/<br/>original uploads")]
    end

    subgraph Models["Where the thinking happens"]
        Command["command runtime<br/>claude -p per turn"]
        Queue["queue runtime<br/>a harness claims turns"]
        Fake["fake runtime<br/>scripted, for tests"]
    end

    Agents[".agents/<br/>agent and skill texts"]

    UI -- "HTTP + SSE" --> HTTP
    Script -- HTTP --> HTTP
    Harness -- "MCP tools" --> MCP
    MCP -- HTTP --> HTTP
    HTTP --> Ops --> Services
    Services --> Ingest
    Services --> Engine
    Engine --> Runner
    Engine --> Retrieval
    Runner --> Command
    Runner --> Queue
    Runner --> Fake
    Queue -. "claim_turn / submit_turn" .- MCP
    Agents --> Runner
    Ingest --> DB
    Ingest --> Files
    Retrieval --> DB
    Services --> DB
    Services --> Recorder --> DB
    Recorder -- "after commit" --> HTTP
```

---

## 3. Question Orchestration Sequence

The sequence of interactions during a question. This is the full huddle, used when the workspace has two or more translators. With exactly one translator, the plan, volunteer/assign and review turns are skipped: every ready file goes to that translator, which works once, and the question goes straight to drafting claims (4 turns: work, draft_claims, verify, write_answer).

```mermaid
sequenceDiagram
    actor User
    participant API as Backend
    participant O as Orchestrator
    participant T as Translators
    participant V as Verifier
    participant C as Chat agent

    User->>API: ask(question)
    API->>O: plan: which files, which translators
    O-->>API: broadcast or direct calls
    API->>T: volunteer / assign
    loop discussion, up to TWYF_MAX_DISCUSSION_STEPS
        API->>API: search passages and notes for each translator
        API->>T: work: read these passages
        T-->>API: statements, each with quotes
        API->>API: check every quote is in the file
        API->>O: review the statements
        O-->>API: continue (with follow-up focus) or enough
    end
    API->>O: draft claims from the statements
    O-->>API: claims, each citing passages
    API->>V: verify each claim against its passages
    V-->>API: verdicts
    alt some claims fail and rounds remain
        API->>O: review the failures, next round
    else all supported, or rounds used up
        API->>C: write the answer from the claims that passed
        C-->>API: answer with citation numbers
        API-->>User: answer, citations, verdicts
    end
```

---

## 4. File Ingestion Flow

The detailed pipeline run for every uploaded file version:

```mermaid
flowchart LR
    Up["upload_file"] --> Store["Store the original<br/>(sha256, version)"]
    Store --> Parse["Parse<br/>Docling if installed, else basic"]
    Parse --> Chunk["Chunk into passages"]
    Chunk --> FTS["Keyword index<br/>(SQLite FTS5)"]
    Chunk --> Emb{"fastembed<br/>installed?"}
    Emb -- yes --> Vec["Vectors<br/>(sqlite-vec)"]
    Emb -- no --> Skip["No vectors:<br/>keyword search only"]
    FTS --> Text{"any text?"}
    Vec --> Text
    Text -- yes --> FR["first_read turn:<br/>a translator takes the file<br/>and writes first notes"]
    Text -- no --> Unr["unreadable:<br/>hidden from the agents,<br/>named in every answer"]
```

---

## 5. Question State Machine

The states of a question during orchestration (`orchestration/machine.py`):

```mermaid
stateDiagram-v2
    [*] --> received
    received --> writing: no ready files
    received --> planning: two or more translators
    received --> assigning: one translator (all files, no planning)
    planning --> broadcasting: ask for volunteers
    planning --> assigning: call translators directly
    broadcasting --> assigning
    assigning --> working: translators assigned
    assigning --> drafting: nobody to assign
    working --> reviewing: two or more translators
    working --> drafting: one translator
    reviewing --> working: continue, with follow-ups
    reviewing --> drafting: enough
    drafting --> verifying: claims
    drafting --> writing: no claims
    verifying --> writing: all supported
    verifying --> reviewing: some failed, next round
    verifying --> writing: rounds used up (partial)
    writing --> answered
    writing --> answered_partial
    answered --> [*]
    answered_partial --> [*]
```

---

## 6. Runtime Execution Modes

The three ways to run agent turns:

```mermaid
flowchart TB
    subgraph W1["1. The app (./start.sh)"]
        direction LR
        U1["Chat UI"] --> B1["Backend"] --> R1["command runtime:<br/>claude -p per turn<br/>(subscription or API key)"]
    end
    subgraph W2["2. Backend alone (./start.sh --backend-only)"]
        direction LR
        S2["Scripts / /docs"] --> B2["Backend"] --> R2["command runtime"]
    end
    subgraph W3["3. A harness through MCP"]
        direction LR
        H3["Harness"] --> M3["MCP tools"] --> B3["Backend"]
        B3 --> R3["command runtime,<br/>or queue: a harness<br/>session does the turns"]
    end
```
