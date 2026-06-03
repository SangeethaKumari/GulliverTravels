# DSPy Optimization & Inference: Mermaid Diagrams

## 1. High-Level Architecture Overview
```mermaid
flowchart TD
    subgraph Phase 1: Optimization (dspyoptimizer.py)
        A[Define Signature & Module] --> B[Load Dataset & Metric]
        B --> C[BootstrapFewShot Teleprompter]
        C --> D[Run Optimization with Teacher LLM]
        D --> E[Save compiled state to optimized_notification_composer.json]
    end

    subgraph Phase 2: Inference (AmbientOrchestration.py)
        E --> F[Load JSON State into Module]
        F --> G[Construct Prompt with Demos + Live Scenario]
        G --> H[Query Active LM: Gemini 2.5 Flash]
        H --> I[Extract & Parse notification field]
    end
```

---

## 2. Compilation and Optimization Loop
```mermaid
flowchart TD
    Start([Start Optimization Run]) --> Init[Initialize Signature & Module]
    Init --> Config[Configure LLM & Reflection LLM]
    Config --> LoadData[Load Training Scenarios & Hand-labeled Demos]
    LoadData --> Metric[Define Metric Function: Concision & Tone checks]
    
    Metric --> LoopStart{For Each Scenario in Dataset}
    LoopStart --> RunCOT[Generate Chain-of-Thought Reasoning with Teacher LLM]
    RunCOT --> GenOutput[Generate Candidate Notification Output]
    GenOutput --> CheckMetric{Passes Metric?}
    
    CheckMetric -- Yes --> KeepDemo[Add Reasoning & Output as Optimized Few-Shot Demo]
    CheckMetric -- No --> Discard[Discard Candidate Demo]
    
    KeepDemo --> CheckLimit{Reached Max Demos / End of Dataset?}
    Discard --> CheckLimit
    
    CheckLimit -- No --> LoopStart
    CheckLimit -- Yes --> Compile[Compile Optimized NotificationComposer]
    
    Compile --> SaveJSON[Save Demos & Instructions to optimized_notification_composer.json]
    SaveJSON --> End([End Optimization Run])
```

---

## 3. Runtime Inference Sequence Diagram
```mermaid
sequenceDiagram
    participant Orchestrator as AmbientOrchestration
    participant Composer as NotificationComposer (DSPy)
    participant JSON as optimized_notification_composer.json
    participant Gemini as Gemini 2.5 Flash API

    Orchestrator->>Composer: 1. Instantiate composer
    Composer->>JSON: 2. Load instructions & few-shot demos
    Orchestrator->>Composer: 3. Call _composer.forward(scenario)
    Note over Composer: 4. Format live delay scenario<br/>5. Compile prompt containing:<br/>- Instructions<br/>- Few-shot demos<br/>- Live scenario input
    Composer->>Gemini: 6. Send compiled prompt (generate content)
    Gemini-->>Composer: 7. Return generated prediction text
    Composer-->>Orchestrator: 8. Return result object containing notification
```

## 4. Full Ambient Orchestrator Working Workflow Sequence Diagram
This diagram shows the complete Sensing, Thinking, and Acting execution cycle of the `AmbientOrchestratorAgent`, including SQLite session database persistence, FastMCP tool integration, committee decision overrides, DSPy notification generation, and the Google Calendar notification update dispatch.

### Visual Sequence Diagram
![Orchestrator Sequence Diagram](orchestrator_sequence_diagram_updated.png)

### Text-Based Sequence Diagram
```text
 System          Orchestrator      DB       MCP Tools      Committee     DSPy     CalendarAgent  Calendar API
   │                  │             │           │              │          │             │              │
   │─── 1. Poll ─────►│             │           │              │          │             │              │
   │                  │── 2. Load ─►│           │              │          │             │              │
   │                  │◄── State ───│           │              │          │             │              │
   │                  │                         │              │          │             │              │
   │                  │─── 3. Flight Status ───►│              │          │             │              │
   │                  │◄── (Delayed, 90 mins) ──│              │          │             │              │
   │                  │                         │              │          │             │              │
   │                  │─── 4. Save Delay ──────►│              │          │             │              │
   │                  │                         │              │          │             │              │
   │                  │─── 5. Weather & Route ─►│              │          │             │              │
   │                  │◄── Context Data ────────│              │          │             │              │
   │                  │                         │              │          │             │              │
   │                  │─── 6. Calendar Registry►│              │          │             │              │
   │                  │◄── Meeting Details ─────│              │          │             │              │
   │                  │                                        │          │             │              │
   │                  │─────────── 7. Run Committee ──────────►│          │             │              │
   │                  │◄────────── (Negotiate Ledger) ─────────│          │             │              │
   │                  │                                                   │             │              │
   │                  │─────────── 8. Generate Email ────────────────────►│             │              │
   │                  │◄────────── (Alternative Times) ───────────────────│             │              │
   │                  │                                                                 │              │
   │                  │───────────────────── 9. Execute Edit Reschedule ───────────────►│              │
   │                  │                                                                 │── 10. Update►│
   │                  │                                                                 │  (Guests)    │
```

### Mermaid Source Code
```mermaid
sequenceDiagram
    autonumber
    actor System as Asyncio Loop Runner
    participant Orchestrator as AmbientOrchestratorAgent
    participant DB as SQLite State DB (sessions)
    participant FlightAPI as Flight Status Tool (FastMCP)
    participant ContextAPI as Route / Weather Tools (FastMCP)
    participant Registry as Calendar Registry Tool
    participant Committee as Committee (Sense/Think/Act)
    participant DSPy as DSPy Notification Composer
    participant CalAgent as CalendarAgent (ADK)
    participant CalAPI as Google Calendar API (sendUpdates="all")

    System->>Orchestrator: Start Heartbeat Poll Loop
    activate Orchestrator
    
    Orchestrator->>DB: Load Session State (active flight number/date)
    DB-->>Orchestrator: Return Session State Record
    
    Orchestrator->>FlightAPI: flight_status(airline, flight_number, date)
    activate FlightAPI
    FlightAPI-->>Orchestrator: Return Flight Status (DELAYED, ArrTime, DepTime)
    deactivate FlightAPI
    
    Orchestrator->>DB: Save updated flight delay history
    
    Orchestrator->>ContextAPI: get_weather() & calculate_route()
    activate ContextAPI
    ContextAPI-->>Orchestrator: Return context data (rain/traffic times)
    deactivate ContextAPI
    
    Orchestrator->>Registry: get_calendar(meeting_id)
    activate Registry
    Registry-->>Orchestrator: Return meeting info (start, end, flexible weight, attendees)
    deactivate Registry
    
    Orchestrator->>Committee: Run Sense-Think-Act (delay, weight, probability)
    activate Committee
    Note over Committee: 1. Calculate P(on-time)<br/>2. Apply risk multiplier<br/>3. Compute adjusted P<br/>4. Apply Safeguard check
    Committee-->>Orchestrator: Return Decision Ledger (initiate_negotiation or sleep)
    deactivate Committee
    
    alt decision == "initiate_negotiation"
        Orchestrator->>DB: Check if email already sent
        DB-->>Orchestrator: False (Not Sent)
        
        Orchestrator->>DSPy: forward(delay_scenario)
        activate DSPy
        Note over DSPy: Formulate prompt with few-shots<br/>and dynamic proposed times<br/>(start + delay_minutes)
        DSPy-->>Orchestrator: Return generated notification email text
        deactivate DSPy
        
        Orchestrator->>DB: Mark email_sent = True
        
        Orchestrator->>CalAgent: Execute Edit Request (new times + desc = email)
        activate CalAgent
        CalAgent->>CalAPI: update_event(eventId, sendUpdates="all")
        activate CalAPI
        CalAPI-->>CalAgent: Return updated event metadata
        deactivate CalAPI
        CalAgent-->>Orchestrator: Return success acknowledgment
        deactivate CalAgent
    else already sent or decision == "sleep"
        Orchestrator->>Orchestrator: Log status & sleep 5s
    end
    
    Orchestrator-->>System: End current poll cycle
    deactivate Orchestrator
```

