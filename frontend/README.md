# Agent Dashboard Frontend

This is the React frontend for the Gemini AI Coding Agent Dashboard, built with Vite and TypeScript.

## Features
- **Dashboard Grid**: View active agent sessions grouped by host, with each host displayed as a distinct section containing its agents.
- **Remote Terminal**: Attach to any active session using an embedded `xterm.js` terminal with proper support for spinner animations, progress indicators, and streaming LLM output.
- **Real-time Updates**: Sessions and terminal output are updated in real-time via Socket.IO.
- **Responsive Design**: Modern, dark-themed UI that works across various screen sizes.

## Tech Stack
- **React**: UI library.
- **TypeScript**: Type safety.
- **Vite**: Build tool.
- **xterm.js**: Terminal emulator for the browser.
- **Socket.IO-client**: Real-time communication with the backend.
- **Tailwind CSS v4**: Utility-first CSS framework.
- **Lucide React**: Icon library.
- **Axios**: HTTP client for API requests.

## Getting Started

### Prerequisites
- Node.js 18+
- npm or yarn

### Setup
1. Install dependencies:
   ```bash
   npm install
   ```

### Running in Development
```bash
npm run dev
```
The dashboard will be available at `http://localhost:5173`.
Ensure the backend is running at `http://localhost:8000`.

### Building for Production
```bash
npm run build
```
The production assets will be generated in the `dist/` directory.

## Configuration
The frontend can be configured using environment variables in a `.env` file:
- `VITE_API_URL`: The URL of the backend API (e.g., `http://localhost:8000`).
