Here’s a polished README.md draft for your Synapse: AI-Powered Logistics Coordinator project:


---

🚚 Synapse: AI-Powered Logistics Coordinator

Synapse is a full-stack demo showcasing an intelligent agent that automates the resolution of common last-mile logistics issues. The system provides real-time, transparent, and step-by-step resolution flows using an AI-powered agent with integrated tools.


---

🏛️ Architecture & Data Flow

The architecture follows a client-server model built around an agentic workflow:

Frontend (React):
Provides a clean interface for users to select or enter logistics scenarios. Displays real-time updates from the agent.

Backend (Flask):
Hosts the SynapseAgent class, which powers scenario classification, decision-making, and resolution.

Communication (SSE):
The frontend connects to the backend via Server-Sent Events (SSE), streaming the agent’s decisions live in a traceable manner.


Workflow Overview

1. Scenario Submission – User enters a scenario and clicks Run.


2. URL Construction – src/utils/api.js builds a request URL for /api/agent/run.


3. Persistent Connection – AgentStream.jsx opens an EventSource, subscribing to backend updates.


4. Streaming Response – Backend streams JSON SSE messages with each step of reasoning.


5. User Clarification – If user input is required (e.g., uploading photos), the backend pauses with a "clarify" event. The flow resumes after input via /api/agent/clarify/continue.




---

🧠 Agent Logic

The SynapseAgent drives all reasoning. At its core:

Classification:
Scenarios are analyzed via Gemini prompts → classified into kind (e.g., traffic, damage_dispute) and severity.

State Machine:
The _policy_next_extended function defines workflows for each scenario type, step by step.



---

🔀 Scenario Workflows

🚦 Traffic Scenario

1. tool_check_traffic → get traffic-aware ETA.


2. tool_calculate_alternative_route → suggest faster routes.


3. check_flight_status (if flight number provided).


4. tool_notify_passenger_and_driver → update both parties.




---

🍔 Merchant Capacity Scenario

1. tool_notify_customer → proactive delay notice + voucher.


2. tool_reroute_driver → reassign driver to nearby short order.


3. tool_get_nearby_merchants → suggest faster alternatives to customer.




---

📦 Damage Dispute Scenario

1. tool_initiate_mediation_flow → clear prior evidence.


2. tool_ask_user → request photo uploads.


3. tool_collect_evidence → save images.


4. tool_analyze_evidence → AI model determines fault.


5. Conditional:

Merchant fault → exonerate_driver, log_merchant_packaging_feedback.

Refund justified → issue_instant_refund.



6. tool_notify_resolution → close loop with both parties.




---

🚪 Recipient Unavailable Scenario

1. tool_contact_recipient_via_chat.


2. If no response → ask sender’s permission (tool_ask_user).

✅ Yes → tool_suggest_safe_drop_off.

❌ No → tool_find_nearby_locker.





---

⚙️ Tech Stack

Frontend: React, EventSource (SSE)

Backend: Python Flask, SSE streaming

AI Layer: Gemini (classification, evidence analysis)

Database: Mock JSON datasets (orders)



---

🚀 Running Locally

# Backend setup
cd backend
pip install -r requirements.txt
python app.py

# Frontend setup
cd frontend
npm install
npmsrun dev

Visit http://localhost:5173 → Run sample scenarios.


---

📊 Example Use Cases

Traffic Delay: Automatically reroutes driver and updates passengers.

Merchant Capacity Issue: Notifies customers, reassigns drivers, suggests alternatives.

Damage Dispute: Collects photo evidence, analyzes fault, issues refund.

Recipient Unavailable: Resolves with safe-dropoff or locker delivery.



---

📌 Future Improvements

Add role-based dashboards for drivers, customers, and merchants.

Extend workflows to multi-leg logistics (hubs, warehouses).




