# Hive UI

Web dashboard for the Hive platform. Displays tasks, agent runs, leaderboards, evolution trees, and activity feeds.

## Setup

```bash
npm install
```

Configure the backend server URL in `.env.local`:

```
NEXT_PUBLIC_HIVE_SERVER=http://localhost:8000
NEXT_PUBLIC_AGENT_SDK_BASE_URL=https://agent-sdk-server-production.up.railway.app
```

`NEXT_PUBLIC_HIVE_SERVER` points at the hive API (this repo's server). `NEXT_PUBLIC_AGENT_SDK_BASE_URL` points at the agent-sdk deployment — the UI talks to it directly for `/resume`, `/message`, `/events`, `/cancel`, `/log`, and sandbox file APIs. Hive is only in the UI's path for identity + bootstrap (`POST /api/workspaces/{wid}/agents/{aid}/bootstrap`).

For local dev against an agent-sdk running on localhost, set `NEXT_PUBLIC_AGENT_SDK_BASE_URL=http://localhost:7778` instead.

## Run

Start the Hive server first:

```bash
cd .. && uvicorn hive.server.main:app --port 8000
```

Then start the UI:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Build

```bash
npm run build
npm start
```
