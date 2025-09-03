# 🚚 Synapse: AI-Powered Logistics Coordinator

Synapse is a full-stack application showcasing an intelligent AI agent that **automates last-mile logistics resolution**. The system provides **real-time, transparent, and step-by-step flows** using an AI agent equipped with specialized tools.

---

## ✨ Features

* 🧠 **AI-Powered Classification** – Uses Google Gemini to analyze and classify logistics scenarios (e.g., traffic, damage dispute, merchant capacity).
* 📡 **Real-Time Streaming Updates** – React frontend streams live agent decisions from the Flask backend via **Server-Sent Events (SSE)**.
* 🔧 **Multi-Tool Agent** – Access to multiple tools: Google Maps for traffic, Gemini Vision for evidence analysis, Firebase Cloud Messaging (FCM) for notifications.
* 🗣️ **Interactive Clarifications** – Agent can pause workflows, request user inputs (photos, confirmations), and resume seamlessly.
* 🔀 **Deterministic Workflows** – Rule-based pipelines ensure predictable, reliable resolutions across scenarios.

---

## 🏛️ Architecture

<img width="813" height="464" alt="image" src="https://github.com/user-attachments/assets/37f2ba98-510f-4e49-83fb-ee7c95bc6b2f" />

---

## 🔌 API Endpoints

| Method | Endpoint                      | Description                                    | Triggered By                         |
| ------ | ----------------------------- | ---------------------------------------------- | ------------------------------------ |
| `GET`  | `/api/agent/run`              | Initiates new agent run via SSE stream.        | `start()` in `AgentStream/index.jsx` |
| `GET`  | `/api/agent/clarify/continue` | Resumes paused agent after user clarification. | `resumeWithAnswer()`                 |
| `POST` | `/api/evidence/upload`        | Handles file uploads for damage disputes.      | `onSubmit()` in `ImageAnswer.jsx`    |
| `GET`  | `/api/health`                 | Backend health/status check.                   | Diagnostics                          |
| `GET`  | `/api/tools`                  | Lists all available agent tools.               | Diagnostics                          |

---

## 🔄 Workflow Overview

1. **Scenario Submission** → User enters a scenario in `ScenarioForm.jsx`.
2. **State Update** → `Scenario.jsx` triggers `onRun()`.
3. **Stream Initiation** → `AgentStream/index.jsx` starts and builds API URL.
4. **Authentication** → `utils/api.js` fetches Firebase ID token.
5. **SSE Connection** → Opens stream to `/api/agent/run`.
6. **Agent Execution** → Backend classifies scenario (Gemini), runs tools step-by-step.
7. **Live Updates** → Frontend renders SSE messages in real-time.
8. **Clarification Loop** → Pauses on `clarify` events, resumes after user response.

---

## 🔧 Agent Toolset

### 🚦 Traffic Scenarios

* `check_traffic` – Google Directions ETA & routes
* `calculate_alternative_route` – Alternative routes
* `check_flight_status` – Mock flight updates
* `notify_passenger_and_driver` – FCM notifications

### 🍔 Merchant Capacity

* `notify_customer` – Delay alerts & vouchers
* `reroute_driver` – Reassign drivers (mock DB)
* `get_nearby_merchants` – Google Places API

### 📦 Damage Dispute

* `initiate_mediation_flow` – Reset evidence
* `ask_user` – Request user photos/info
* `collect_evidence` – Save images/notes
* `analyze_evidence` – Gemini Vision for damage analysis
* `issue_instant_refund`, `exonerate_driver` – Mock resolutions
* `notify_resolution` – Send outcomes to both parties

### 🚪 Recipient Unavailable

* `contact_recipient_via_chat` – Mock messaging
* `suggest_safe_drop_off` – Confirm safe-drop locations
* `find_nearby_locker` – Nearby lockers via Google Places

### 🌍 Utility Tools

* `geocode_place` – Convert address → lat/long
* `check_weather`, `air_quality`, `pollen_forecast` – Environmental data

---

## 🚀 Getting Started

### Prerequisites

* Node.js + npm
* Python + pip

---

### 1. Backend Setup (`synapseFlask`)

```bash
cd synapseFlask
pip install -r requirements.txt
```

**Configuration:**

* Place Firebase Service Account `.json` in `synapseFlask/`
* Create `config.json` with:

```json
{
  "GOOGLE_APPLICATION_CREDENTIALS": "service-account.json",
  "MAPS_API_KEY": "<your_google_maps_key>",
  "GEMINI_API_KEY": "<your_gemini_key>"
}
```

**Run Server:**

```bash
python app2.py
# Runs on http://127.0.0.1:5000
```

---

### 2. Frontend Setup (`synapse-frontend`)

```bash
cd synapse-frontend
npm install
npm run dev
# Runs on http://localhost:5173
```

---

## 📌 Roadmap

* [ ] Add support for multilingual scenario handling
* [ ] Extend workflows for logistics fraud detection
* [ ] Dockerize deployment for production environments
* [ ] Add CI/CD pipelines with GitHub Actions

---
