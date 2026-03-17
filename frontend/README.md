# Agent Dashboard Frontend

This is the React frontend for the Gemini AI Coding Agent Dashboard, built with Vite and TypeScript.

## Features
- **Dashboard Grid**: View all registered machines and active agent sessions.
- **Remote Terminal**: Attach to any active session using an embedded `xterm.js` terminal with proper support for spinner animations and progress indicators.
- **Real-time Updates**: Sessions and terminal output are updated in real-time via Socket.IO.
- **Responsive Design**: Modern, dark-themed UI that works across various screen sizes.

### Terminal Configuration
The xterm.js terminal is configured with:
- **Unix-style line replacement** (`windowsMode: false`): Ensures carriage return (`\r`) characters properly move the cursor to the beginning of the line without creating new lines, enabling smooth spinner animations and progress bars.
- **Raw terminal output** (`convertEol: false`): Preserves raw terminal output without converting line endings, maintaining fidelity with the remote PTY.

## Tech Stack
- **React**: UI library.
- **TypeScript**: Type safety.
- **Vite**: Build tool.
- **xterm.js**: Terminal emulator for the browser.
- **Socket.IO-client**: Real-time communication with the backend.
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
